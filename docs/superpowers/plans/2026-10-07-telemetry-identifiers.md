# Telemetry Identifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `production_error` notes keep the Sentry issue title and one sample ADX log message, ticket identifiers included, mask only credentials and emails, and group errors by their real route shapes and type names: no group key holds `[REDACTED:high_entropy]` any more, and only the groups whose keys held it change fingerprint.

**Architecture:** `redact.py` gains `redact_credentials()`: the named detectors plus bare bearer tokens, URL passwords, connection-string keys and JSON secret fields, without the generic high-entropy guess. `telemetry.sanitize()` switches to it, so one key cleaning feeds both the fingerprint and the note: credentials and emails masked, GUIDs, long digit runs and hex ids collapsed to `<guid>`, `<n>`, `<hex>`, route shapes and type names kept. The new `mask()` cleans free text the same way without collapsing identifiers. The fetch carries Sentry `title` and an ADX `message = take_any(body)` column into a new optional `message` field, and the note store masks it at the same trust boundary that already re-checks every field.

**Tech Stack:** Python 3 stdlib (`re`, `urllib.parse`), pytest, bats. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-05-error-monitoring-design.md` (Plan 11; this plan revises its §1 Data policy, §3.2, §3.3, §4 and §8 in Task 5).

## Root cause of `[REDACTED:high_entropy]` (goal A)

`telemetry.sanitize()` (`system/scripts/vaultlib/telemetry.py:175-182`) calls `redact()` on the whole value **before** it collapses GUIDs and numbers. `redact()` ends with the generic secret guess (`system/scripts/vaultlib/redact.py:108-110`): every run of `CANDIDATE = [A-Za-z0-9+/=_-]{32,}` (`redact.py:21`) whose Shannon entropy is at least `ENTROPY_BITS = 4.0` (`redact.py:23`) becomes `[REDACTED:high_entropy]` (`_high_entropy`, `redact.py:31-35`).

- **Routes.** `/` and `-` are token characters, so a span route with no spaces is one token. A bare GUID is 36 characters at 3.88 bits and survives; joined into a path (`api/orders/<GUID>/credential-check`, 64 characters, above 4.0) the whole route is replaced, and the `GUID → <guid>` step never sees it.
- **Type names.** `.` is not a token character, so the namespace survives, but a PascalCase type name of 32 or more characters clears 4.0 alone (for example `VendorAccountSuitabilitySubmissionFetchXML`: 42 characters, above 4.0). Long class names in a real codebase often do.
- **Effect on notes.** A group key that held the marker hashes the literal marker, so every long route with the same status (or every long type name under the same namespace) lands in one note, and that note's reopen KQL drops the redacted condition. The tests reproduce this with generic names: on the old code a long route gives a note such as `shop-prod-adx-a-8513424e6ee9` (`exception: "[REDACTED:high_entropy] 500"`) and a long type name gives `shop-uat-adx-a-2f59495da85c` (`Acme.Core.Plugins.Vendor.[REDACTED:high_entropy]#9908`). Task 2 removes the guess from key cleaning, so these groups split into their real errors (user decision, 2026-10-07).

## Global Constraints

- User decision (2026-10-07), verbatim: "Ticket identifiers are needed and maintaining which env can show them in logs is unnecessary. This isn't PII data." It applies to every source and environment.
- Mask only credential-shaped strings (API keys, bearer tokens, connection strings, passwords) and email addresses. GUIDs, application IDs such as `A1-23B4C-D-56`, numbers, long type names and URL paths stay.
- Group keys drop the high-entropy guess (user decision, 2026-10-07: fix the grouping key). `sanitize` ran `redact()` before its shape steps (query strip, `<guid>`, `<email>`, `<hex>`, `<n>`, 200-character cut); it now runs `redact_credentials()`, which is `redact()` without the guess plus four patterns. A fingerprint therefore changes only where the guess fired (the key held the marker) or where one of the four patterns fires on a raw key (a credential in clear inside a route, scope or module value). Every other fingerprint stays byte-identical; `test_vault_fingerprints_without_the_marker_do_not_change` pins six, computed by the code before Task 2.
- Notes whose key held the marker get no migration. No row hashes to their fingerprints after Task 2, so their `last_seen` stops moving and `resolve_stale` marks them `resolved` after the existing 7-day quiet rule; they are never deleted. The split groups start as new notes with counts from the next fetch window (no backfill) and go through the capped Sentry cover lookup like any new group.
- `redact()` called with its default argument behaves exactly as before (digests, inbox copies and meeting notes use it).
- Group keys in notes keep their shape (`<guid>`, `<n>`, `<hex>`, `<email>`, query strings dropped) so one group covers many tickets and the reopen KQL keeps dropping placeholder conditions.
- `message` is masked, folded to one line and cut at 500 characters after masking. State and the run log hold no free text.
- Verify with no network: `python3 -m pytest system/tests/python -q` and `bats system/tests/telemetry.bats`.

## Review Focus

1. Fingerprints: the three vault groups without the marker keep their note file names, and the two long GUID routes that both landed in `a-8513424e6ee9` now land in two notes with `<guid>` route shapes (Task 2, `test_vault_fingerprints_without_the_marker_do_not_change`, `test_marker_groups_split_into_real_routes_and_type_names`).
2. A log row with a null or missing `Body`, and every span: no `message:` line, and the note still validates (Task 2, `test_marker_groups_split_into_real_routes_and_type_names`; Task 3, `test_existing_note_gains_message_and_keeps_it`).
3. A message with newlines, tabs, double quotes or backslashes: one frontmatter line that parses back to the folded text (Task 3, `test_message_is_one_line_and_round_trips`).
4. A credential next to the 500-character cut: masked before the cut, so no fragment survives (Task 2, `test_mask_edges`).
5. A structured or JSON `Body` (`{"password":"…"}`), and `<private>` tags in a body, unterminated included: the secret field and the private span are masked (Task 1 parametrize row, Task 2 `test_mask_edges`).
6. A later row or issue with no message after one with a message, and a status change by the run: the earlier message stays (Task 3, `test_existing_note_gains_message_and_keeps_it`).

## File Structure

| File | Change |
|---|---|
| `system/scripts/vaultlib/redact.py` | `redact(text, high_entropy=True)`; new `redact_credentials(text)` and its four patterns |
| `system/scripts/vaultlib/telemetry.py` | `sanitize` (credentials and emails masked, no high-entropy guess), `mask`; `kql_logs` returns `message` |
| `system/scripts/vaultlib/telemetry_store.py` | `message` in `NOTE_FIELDS`, `_clean` and `upsert` |
| `system/schemas/production_error.md` | optional `message` field; body text |
| `system/scripts/vaultlib/sentry.py` | keep `title` |
| `system/scripts/vaultlib/telemetry_run.py` | `message` from the row or issue (Task 4); keys and fingerprints keep calling `t.sanitize` |
| `system/tests/fixtures/telemetry/kusto-logs.json`, `system/tests/telemetry.bats` | a `message` column and one end-to-end check |
| `system/tests/python/test_redact.py`, `test_telemetry_core.py`, `test_telemetry_store.py`, `test_telemetry_schema.py`, `test_sentry.py`, `test_telemetry_run.py` | tests below |
| `docs/superpowers/specs/2026-10-05-error-monitoring-design.md`, `README.md` | data policy text |

---

### Task 1: `redact_credentials` and the `high_entropy` switch

**Files:**
- Modify: `system/scripts/vaultlib/redact.py:19-20` (patterns), `:89-111` (`redact`), new function before `ASSIGNMENT_EQUALS` (`:114`)
- Test: `system/tests/python/test_redact.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `redact(text: str, high_entropy: bool = True) -> tuple[str, int]` (default unchanged); `redact_credentials(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_redact.py`, change the import line to:

```python
from vaultlib.redact import named_kinds, redact, redact_credentials
```

Append:

```python
LONG_NAME = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
GUID_PATH = "api/orders/3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b/credential-check"


def test_high_entropy_guess_hits_long_names_and_guid_paths_and_can_be_skipped():
    """The cause of [REDACTED:high_entropy] in telemetry notes: CANDIDATE takes / and - as token characters, so a GUID
    inside a path joins one 64-character token above ENTROPY_BITS; a long PascalCase type name clears it alone."""
    assert redact(GUID_PATH) == ("[REDACTED:high_entropy]", 1)
    assert redact(LONG_NAME) == ("Shop.Plugins.[REDACTED:high_entropy]", 1)
    assert redact("3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b")[1] == 0
    assert redact(GUID_PATH, high_entropy=False) == (GUID_PATH, 0)
    assert redact(LONG_NAME, high_entropy=False) == (LONG_NAME, 0)
    assert redact("Zq8xT2mN7vB4kL9pR3wY6cH1jF5dS0aE password=x", high_entropy=False) == (
        "Zq8xT2mN7vB4kL9pR3wY6cH1jF5dS0aE password=[REDACTED:assignment]", 1)


@pytest.mark.parametrize("text, secret, marker", [
    ("call failed: Bearer Zm9vYmFyYmF6cXV4MTIzNDU2 rejected", "Zm9vYmFyYmF6cXV4MTIzNDU2", "Bearer [REDACTED:bearer] rejected"),
    ("postgres://app:pgpass99@db:5432/x", "pgpass99", "postgres://app:[REDACTED:userinfo]@db"),
    ("Server=db;Pwd=s3cretPwd;Database=x", "s3cretPwd", "Pwd=[REDACTED:connection];Database=x"),
    ("AccountName=a;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==;EndpointSuffix=core.windows.net", "Zm9vYmFyQUNDT1VOVEtFWQ",
     "AccountKey=[REDACTED:connection];EndpointSuffix"),
    ("https://a.blob.core.windows.net/c/f?sv=2022&sig=AbCdEfSAS&se=2026", "AbCdEfSAS", "sig=[REDACTED:connection]&se=2026"),
    ("Server=db;Password=hunter2;Database=x", "hunter2", "Password=[REDACTED:assignment]"),
    ('{"user":"a","password":"hunter2"}', "hunter2", '"password":"[REDACTED:json]"'),
    ('{"ticketGuid":"3f2b","apiKey": "k-123"}', "k-123", '"apiKey": "[REDACTED:json]"'),
    ("key AKIAIOSFODNN7EXAMPLE here", "AKIAIOSFODNN7EXAMPLE", "key [REDACTED:aws_key] here"),
])
def test_redact_credentials_masks_credential_shapes(text, secret, marker):
    out = redact_credentials(text)
    assert secret not in out and marker in out


def test_redact_credentials_keeps_identifiers_and_prose():
    text = (f"Ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b for A1-23B4C-D-56 in {LONG_NAME} at {GUID_PATH}; "
            'the bearer of bad news {"tokenCount":"5"}')
    assert redact_credentials(text) == text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_redact.py -q`
Expected: collection error `ImportError: cannot import name 'redact_credentials'`.

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/redact.py`, after the `ASSIGNMENT = …` line (`:20`), add:

```python
BARE_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]{16,}=*")
USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@]+:)[^/\s@]+@")
CONNECTION = re.compile(r"(?i)\b(pwd|accountkey|sharedaccesskey|sharedaccesssignature|sig|client_secret|access_token"
                        r"|refresh_token)(\s*=\s*)(?!\[REDACTED)([^;&\s]+)")
JSON_SECRET = re.compile(r'(?i)("(?:password|passwd|pwd|(?:client_)?secret|(?:access_|refresh_)?token|api[_-]?key'
                         r'|accountkey)"\s*:\s*)"[^"]*"')
```

Replace the head of `redact` and its last four lines:

```python
def redact(text: str, high_entropy: bool = True) -> tuple:
    """Return (redacted_text, redaction_count). high_entropy=False skips the generic high-entropy guess."""
```

```python
    text = sub(BEARER, r"\1[REDACTED:bearer]", text)
    text = sub(ASSIGNMENT, r"\1\2[REDACTED:assignment]", text)
    if not high_entropy:
        return text, count
    before = text
    text = CANDIDATE.sub(_high_entropy, text)
    count += text.count("[REDACTED:high_entropy]") - before.count("[REDACTED:high_entropy]")
    return text, count


def redact_credentials(text: str) -> str:
    """Telemetry text (error monitoring spec §1): credential-shaped strings only. The named detectors plus bare bearer
    tokens, URL passwords, connection-string keys and JSON secret fields; no high-entropy guess, which also hits
    GUID-bearing URL paths and long type names."""
    text, _ = redact(text, high_entropy=False)
    text = BARE_BEARER.sub(r"\1[REDACTED:bearer]", text)
    text = USERINFO.sub(r"\1[REDACTED:userinfo]@", text)
    text = CONNECTION.sub(r"\1\2[REDACTED:connection]", text)
    return JSON_SECRET.sub(r'\1"[REDACTED:json]"', text)
```

The four new patterns are used only by `redact_credentials`, so `redact(text)` output is unchanged for digests, inbox copies and meetings.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_redact.py -q`
Expected: all pass, including the existing `test_safe_text_untouched`, `test_high_entropy_string` and `test_named_kinds_*`.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/redact.py system/tests/python/test_redact.py
git commit -m "feat(redact): redact_credentials masks credential shapes only, no high-entropy guess"
```

### Task 2: Group keys without the high-entropy guess, `mask`, and the log message column

**Files:**
- Modify: `system/scripts/vaultlib/telemetry.py:10` (import), `:112-124` (`kql_logs`), `:175-182` (`sanitize`)
- Test: `system/tests/python/test_telemetry_core.py`, `system/tests/python/test_telemetry_store.py`, `system/tests/python/test_telemetry_run.py`

**Interfaces:**
- Consumes: `redact_credentials(text) -> str` (Task 1).
- Produces: `sanitize(value) -> str`, the one key cleaning that both the fingerprint and the note use, now without the high-entropy guess; `mask(value, limit: int = 500) -> str`; `kql_logs` rows carry a `message` column. `_adx_groups`, `_sentry_groups`, `event_id` and `Store._clean` keep calling `sanitize` unchanged.

This task changes the fingerprint of every group whose key held `[REDACTED:high_entropy]` and of no other group (Global Constraints).

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_telemetry_core.py`, replace line 35 (`    assert "Body" not in q`) with:

```python
    assert "body = tostring(Body)" in q and "message = take_any(body)" in q
```

Append:

```python
GUID = "3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b"
LONG_SCOPE = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
GUID_ROUTE = f"api/orders/{GUID}/credential-check"


def test_sanitize_keeps_long_type_names_and_route_shapes():
    assert t.sanitize(LONG_SCOPE) == LONG_SCOPE
    assert t.sanitize(GUID_ROUTE) == "api/orders/<guid>/credential-check"
    assert t.sanitize("A1-23B4C-D-56") == "A1-23B4C-D-56"
    assert t.sanitize("db password=hunter2") == "db password=[REDACTED:assignment]"
    assert t.sanitize("call Bearer Zm9vYmFyYmF6cXV4MTIzNDU2") == "call Bearer [REDACTED:bearer]"


def test_mask_keeps_identifiers_and_masks_credentials_and_emails():
    dirty = (f"Ticket {GUID} for application A1-23B4C-D-56 failed for bob@example.com and bob%40example.com "
             "Authorization: Bearer abc.def.ghi Bearer Zm9vYmFyYmF6cXV4MTIzNDU2 password=hunter2 "
             "Server=db;Pwd=s3cretPwd;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==;Database=x "
             "https://x.example.com/p?sig=AbCdEfSAS postgres://app:pgpass99@db/x AKIAIOSFODNN7EXAMPLE")
    m = t.mask(dirty)
    assert m.startswith(f"Ticket {GUID} for application A1-23B4C-D-56 failed for <email> and <email> ")
    for s in ["bob", "abc.def.ghi", "Zm9vYmFyYmF6cXV4MTIzNDU2", "hunter2", "s3cretPwd", "Zm9vYmFyQUNDT1VOVEtFWQ",
              "AbCdEfSAS", "pgpass99", "AKIAIOSFODNN7EXAMPLE"]:
        assert s not in m, s
    assert t.mask(f"in {LONG_SCOPE} at {GUID_ROUTE}") == f"in {LONG_SCOPE} at {GUID_ROUTE}"


def test_mask_edges():
    assert t.mask(None) == "" and t.mask("") == ""
    assert t.mask("line one\nline two\t  three") == "line one line two three"
    near_cut = "x" * 490 + " password=hunter2 tail"
    assert "hunter2" not in t.mask(near_cut) and len(t.mask(near_cut)) == 500
    assert len(t.mask("y" * 900)) == 500
    assert t.mask("keep <private>hidden</private> this") == "keep [PRIVATE] this"
    assert t.mask("a <private>open to the end") == "a [PRIVATE]"
    j = t.mask('{"ticketGuid":"' + GUID + '","password":"hunter2"}')
    assert GUID in j and "hunter2" not in j
```

Append to `system/tests/python/test_telemetry_store.py`:

```python
def test_long_type_names_are_not_redacted(vault):
    scope = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
    st = Store(vault); st.load()
    st.upsert(group(exception=f"{scope}#9908", keys={"service": "worker", "scope": scope, "event_id": "9908"}), NOW)
    text = (vault / "raw/telemetry/prod-adx-a-0123456789ab.md").read_text()
    assert "high_entropy" not in text
    assert f'exception: "{scope}#9908"' in text and f"| scope | {scope} |" in text
```

Append to `system/tests/python/test_telemetry_run.py` (it uses the module's existing `GUID` constant):

```python
def _two_signal_source(v, name):
    write(v, f"system/telemetry/{name}.md", ADX.format(covers="").replace('"prod-adx"', f'"{name}"').replace(
        'adx_signals: ["logs"]', 'adx_signals: ["logs", "spans"]\nadx_group_keys: ["app.partition", "app.slice"]'))


def _rows(logs, spans):
    return lambda c, d, kql, n: logs if kql.startswith("Logs") else spans


SPAN_ROW = {"service": "core-api", "status": 500, "n": 1, "first_ts": "2026-10-05T10:00:00Z",
            "last_ts": "2026-10-05T11:00:00Z", "traces": 1, "sample_trace": "0af7651916cd43dd8448eb211c80319c"}


def test_vault_fingerprints_without_the_marker_do_not_change(v, monkeypatch):
    """Groups with no [REDACTED:high_entropy] in their keys: their fingerprints, and so their note file names, must
    not move. The names were computed by the code before Task 2; the test passes before and after it."""
    _two_signal_source(v, "shop-uat-adx")
    _two_signal_source(v, "shop-prod-adx")
    logs = [dict(LOG_ROW, service="core-worker", scope="Acme.Platform.Services.MailService", event_id="1800",
                 module_0="Acme.Core.Partitions.Orders.OrderPartition",
                 module_1="Acme.Core.Partitions.Orders.OrderEmailNotificationSlice"),
            dict(LOG_ROW, service="batch-worker", scope="Quartz.Impl.AdoJobStore.ClusterManager", event_id="",
                 module_0="", module_1="")]
    spans = [dict(SPAN_ROW, route="api/vendor/agent-credentials/order-credential-check")]
    monkeypatch.setattr(kusto, "query", _rows(logs, spans))
    assert telemetry_run.main([], v, NOW) == 0
    assert sorted(p.name for p in (v / "raw/telemetry").glob("*.md")) == [
        "shop-prod-adx-a-1ac755ccca34.md", "shop-prod-adx-a-2a9d42e61b13.md", "shop-prod-adx-a-8818b5096c41.md",
        "shop-uat-adx-a-0e5b4bafc506.md", "shop-uat-adx-a-30e079fb650d.md", "shop-uat-adx-a-f7890ec560a5.md"]


def test_marker_groups_split_into_real_routes_and_type_names(v, monkeypatch):
    """Before 2026-10-07 both routes hashed to a-8513424e6ee9 (route key "[REDACTED:high_entropy]") and the long scope
    to a-2f59495da85c; now each lands in its own group under its real shape."""
    _two_signal_source(v, "shop-uat-adx")
    _two_signal_source(v, "shop-prod-adx")
    spans = [dict(SPAN_ROW, route=f"api/orders/{GUID}/credential-check"),
             dict(SPAN_ROW, route=f"api/vendor/agent-credentials/{GUID}/order-credential-check")]
    log = dict(LOG_ROW, service="core-worker", scope="Acme.Core.Plugins.Vendor.VendorAccountSuitabilitySubmissionFetchXML",
               event_id="9908", module_0="", module_1="")
    monkeypatch.setattr(kusto, "query", _rows([log], spans))
    assert telemetry_run.main([], v, NOW) == 0
    tele = v / "raw/telemetry"
    assert not (tele / "shop-prod-adx-a-8513424e6ee9.md").exists()
    assert not (tele / "shop-uat-adx-a-2f59495da85c.md").exists()
    notes = [p.read_text() for p in tele.glob("shop-prod-adx-a-*.md")]
    assert sorted(l for n in notes for l in n.splitlines() if l.startswith("exception:")) == [
        'exception: "Acme.Core.Plugins.Vendor.VendorAccountSuitabilitySubmissionFetchXML#9908"',
        'exception: "api/orders/<guid>/credential-check 500"',
        'exception: "api/vendor/agent-credentials/<guid>/order-credential-check 500"']
    assert all("high_entropy" not in n and "message:" not in n for n in notes)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_store.py system/tests/python/test_telemetry_run.py -q`
Expected: FAIL. `test_kql_filter_and_group_keys_are_quoted` (no `body =`), `test_sanitize_keeps_long_type_names_and_route_shapes` (`Shop.Plugins.[REDACTED:high_entropy]` != the scope), `AttributeError: module 'vaultlib.telemetry' has no attribute 'mask'` in the two mask tests, `test_long_type_names_are_not_redacted` (the store's `_clean` still redacts the scope), and `test_marker_groups_split_into_real_routes_and_type_names` on its first `assert not` (the old code writes `shop-prod-adx-a-8513424e6ee9.md`). `test_vault_fingerprints_without_the_marker_do_not_change` passes: it guards the step below.

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/telemetry.py`, change the import (`:10`):

```python
from .redact import redact_credentials
```

In `kql_logs`, replace the `extend` and `summarize` lines so the function reads:

```python
def kql_logs(src: Source, start: datetime, end: datetime, limit: int = 500) -> str:
    extra = [f"module_{i} = tostring(LogsAttributes[{_q(k)}])" for i, k in enumerate(src.adx_group_keys)]
    by = ["service", "scope", "event_id"] + [f"module_{i}" for i in range(len(src.adx_group_keys))]
    return "\n".join(["Logs",
                      f"| where Timestamp >= {_t(start)} and Timestamp < {_t(end)} and SeverityNumber >= 17",
                      *_filters(src),
                      "| extend service = tostring(ResourceAttributes[\"service.name\"]), "
                      "scope = tostring(LogsAttributes[\"scope.name\"]), event_id = tostring(LogsAttributes[\"logrecord.event.id\"]), "
                      "body = tostring(Body)"
                      + (", " + ", ".join(extra) if extra else ""),
                      f"| summarize n = count(), first_ts = min(Timestamp), last_ts = max(Timestamp), traces = dcount(TraceID), "
                      f"sample_trace = take_any(TraceID), message = take_any(body) by {', '.join(by)}",
                      "| order by n desc",
                      f"| take {limit}"])
```

Replace `sanitize` (`:175-182`) with:

```python
def _text(value) -> str:
    return urllib.parse.unquote(str(value if value is not None else ""))


def sanitize(value) -> str:
    """One group key, as the fingerprint hashes it and the note shows it: credentials and emails masked, IDs and
    numbers collapsed to their shape. No high-entropy guess (dropped 2026-10-07): it hit GUID-bearing routes and long
    type names and merged unrelated errors into one group."""
    text = redact_credentials(_text(value))
    text = QUERY.sub("", text)
    text = GUID.sub("<guid>", text)
    text = EMAIL.sub("<email>", text)
    text = HEX.sub("<hex>", text)
    text = DIGITS.sub("<n>", text)
    return text[:200]


def mask(value, limit: int = 500) -> str:
    """Free text kept for triage (Sentry title, sample log message): credentials and emails masked, identifiers kept,
    whitespace folded to single spaces, cut at `limit` after masking."""
    text = EMAIL.sub("<email>", redact_credentials(_text(value)))
    return " ".join(text.split())[:limit]
```

`event_id`, `trace_id` and `fingerprint` stay as they are, and so does `telemetry_run.py`: `_adx_groups` already hashes the keys `sanitize` returns.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_run.py system/tests/python/test_telemetry_store.py system/tests/python/test_kusto.py -q`
Expected: all pass, including `test_kql_aliases_avoid_reserved_words` (`body` and `message` are not reserved), the unchanged `test_sanitize_and_fingerprint_collapse_ids` and the existing privacy tests (no message is written yet).

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/telemetry.py system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_store.py system/tests/python/test_telemetry_run.py
git commit -m "fix(telemetry): group keys drop the high-entropy guess; marker groups split into real routes and type names"
```

### Task 3: `message` in the note store and the schema

**Files:**
- Modify: `system/scripts/vaultlib/telemetry_store.py:11` (import), `:15-17` (`NOTE_FIELDS`), `:25-44` (`_clean`), `:141-147` (`upsert` frontmatter)
- Modify: `system/schemas/production_error.md`
- Test: `system/tests/python/test_telemetry_store.py`, `system/tests/python/test_telemetry_schema.py`

**Interfaces:**
- Consumes: `mask` (Task 2); `event_id`, `sanitize`, `trace_id`, `kql_reopen` as before.
- Produces: `Store.upsert(g, now)` accepts an optional raw `g["message"]` (masked here, the trust boundary) and writes frontmatter `message`; a later upsert without one keeps the note's earlier `message`.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_telemetry_store.py`, replace the `SECRETS = …` line (`:9`) with:

```python
GUID = "3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b"
APP = "A1-23B4C-D-56"
CREDS = ["AKIAIOSFODNN7EXAMPLE", "hunter2", "s3cretPwd", "Zm9vYmFyQUNDT1VOVEtFWQ", "pgpass99", "Zm9vYmFyYmF6cXV4MTIzNDU2"]
DIRTY = (f"Ticket {GUID} for application {APP} failed for bob@example.com: AKIAIOSFODNN7EXAMPLE password=hunter2 "
         "Server=db;Pwd=s3cretPwd;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==; postgres://app:pgpass99@db/x "
         "Bearer Zm9vYmFyYmF6cXV4MTIzNDU2")
NOTE = "raw/telemetry/prod-adx-a-0123456789ab.md"
```

Replace `test_privacy_nothing_dropped_reaches_disk` (`:57-65`) with:

```python
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

```

`test_store_sanitizes_raw_whitelisted_fields` stays as it is: group keys, `culprit` and `exception` still collapse GUIDs and numbers.

In `system/tests/python/test_telemetry_schema.py`, append:

```python
def test_production_error_message_field_is_known(vault):
    write(vault, "raw/telemetry/prod-sentry-s-101.md", "\n".join([
        "---", "type: production_error", 'service: "api"', 'exception: "KeyError"',
        'message: "KeyError: ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b \\"A1-23B4C-D-56\\""', 'operation_id: "101"',
        'detected_at: "2026-10-05T14:10:00+00:00"', 'kind: "sentry"', 'fingerprint: "s-101"', "---", "# body", ""]))
    idx = Index(vault)
    idx.refresh(full=True)
    rows = idx.connect().execute("SELECT code, message FROM issues WHERE path LIKE 'raw/telemetry/%'").fetchall()
    assert not [r for r in rows if r[0] in ("unknown-field", "schema")], rows
    assert [i for i in issues(vault) if i[0].startswith("raw/telemetry/")] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_telemetry_store.py system/tests/python/test_telemetry_schema.py -q`
Expected: FAIL. `KeyError: 'message'` in the privacy test (the store drops the field), `assert 0 == 1` (no `message:` line) in the round-trip test, `KeyError: 'message'` on the second `read` of `test_existing_note_gains_message_and_keeps_it`, and the schema test lists an `unknown-field` row for `message`.

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/telemetry_store.py`, change the import (`:11`):

```python
from .telemetry import event_id, kql_reopen, mask, sanitize, trace_id
```

Replace `NOTE_FIELDS` (`:15-17`):

```python
NOTE_FIELDS = ("type", "service", "exception", "message", "operation_id", "detected_at", "codebase", "partition",
               "environment", "source", "kind", "fingerprint", "count", "last_seen", "status", "resolved_at", "substatus",
               "regressed", "sentry_issue", "covered", "culprit", "link")
```

In `_clean`, add the `message` check after the `culprit` one:

```python
    if g.get("culprit"):
        g["culprit"] = sanitize(g["culprit"])
    if g.get("message"):
        g["message"] = mask(g["message"])
```

In `upsert`, add `message` to the `fm` dict, right after `"exception": g["exception"],`:

```python
              "message": g.get("message") or prev.get("message"),
```

`prev` is the parsed frontmatter of the existing note (already read above `fm`), so a row without a message keeps the earlier one. `set_status` and `set_covered` rewrite from the note's own frontmatter, and `message` is now in `NOTE_FIELDS`, so they keep it too.

In `system/schemas/production_error.md`, add after the `exception:` field line:

```yaml
  message: {kind: string}
```

and replace the body's last sentence `Aggregates only: no message text or attribute values.` with:

`Holds group keys, counts, times, opaque IDs, links and one message (the Sentry issue title or a sample log message) with ticket identifiers; credentials and emails are masked.`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python/test_telemetry_store.py system/tests/python/test_telemetry_schema.py system/tests/python/test_schema_notes.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/telemetry_store.py system/schemas/production_error.md system/tests/python/test_telemetry_store.py system/tests/python/test_telemetry_schema.py
git commit -m "feat(telemetry): production_error notes keep a masked message"
```

### Task 4: The fetch carries titles and messages

**Files:**
- Modify: `system/scripts/vaultlib/sentry.py:1` (docstring), `:12-13` (`KEEP`)
- Modify: `system/scripts/vaultlib/telemetry_run.py` (`_adx_groups` dict, `_sentry_groups` dict at `:121-128`)
- Modify: `system/tests/fixtures/telemetry/kusto-logs.json`, `system/tests/telemetry.bats`
- Test: `system/tests/python/test_sentry.py`, `system/tests/python/test_telemetry_run.py`

**Interfaces:**
- Consumes: `kql_logs` `message` column (Task 2); `Store.upsert` with `message` (Task 3).
- Produces: ADX log groups and Sentry groups carry a raw `message`, masked by the store.

- [ ] **Step 1: Write the failing tests**

In `system/tests/python/test_sentry.py`, replace line 48:

```python
    assert got[0]["title"] == ISSUE["title"] and "bob@example.com" not in json.dumps(got)
```

In `system/tests/python/test_telemetry_run.py`, replace the block from `GUID = "3f2b8a1e-…"` (`:310`) through the end of `test_privacy_end_to_end` (`:335`; Task 2's tests stay after it) with:

```python
GUID = "3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b"
APP = "A1-23B4C-D-56"
DIRTY = (f"Ticket {GUID} for application {APP} failed for bob@example.com and bob%40example.com "
         "Authorization: Bearer abc.def.ghi Bearer Zm9vYmFyYmF6cXV4MTIzNDU2 password=hunter2 "
         "Server=db;Pwd=s3cretPwd;AccountKey=Zm9vYmFyQUNDT1VOVEtFWQ==;Database=x "
         "https://x.example.com/p?sig=AbCdEfSAS postgres://app:pgpass99@db/x AKIAIOSFODNN7EXAMPLE "
         '{"password":"jsonpass1"}')
NEVER = ["bob@example.com", "bob%40example.com", "abc.def.ghi", "Zm9vYmFyYmF6cXV4MTIzNDU2", "hunter2", "s3cretPwd",
         "Zm9vYmFyQUNDT1VOVEtFWQ", "AbCdEfSAS", "pgpass99", "AKIAIOSFODNN7EXAMPLE", "jsonpass1"]


def test_privacy_end_to_end(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='covers: "prod-sentry"\n').replace(
        'adx_signals: ["logs"]', 'adx_signals: ["logs", "spans"]'))
    log = dict(LOG_ROW, scope=DIRTY, event_id=DIRTY, service=DIRTY, message=DIRTY)
    span = {"service": DIRTY, "route": "GET /a/" + DIRTY, "status": "500", "n": 2, "first_ts": "2026-10-05T10:00:00Z",
            "last_ts": "2026-10-05T11:00:00Z", "traces": 1, "sample_trace": DIRTY}
    monkeypatch.setattr(kusto, "query", lambda c, d, kql, n: [log] if "Logs" in kql.split("\n")[0] else [span])
    issue = dict(_sentry_issue(101), title=DIRTY, culprit=DIRTY, type=DIRTY, environment=DIRTY,
                 metadata={"value": DIRTY, "type": DIRTY}, permalink="https://sentry.example.com/i/101/?sig=AbCdEfSAS")
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [issue])
    monkeypatch.setattr(sentry, "issue_for_trace", lambda *a: None)
    assert telemetry_run.main([], v, NOW) == 0
    assert telemetry_run.main(["--dry-run"], v, NOW + timedelta(hours=1)) == 0
    assert telemetry_run.main([], v, NOW + timedelta(hours=2)) == 0
    out = capsys.readouterr().out
    files = [p for p in v.rglob("*") if p.is_file() and ("raw/telemetry" in str(p) or "system/logs" in str(p))]
    blobs = [out] + [p.read_text() for p in files]
    assert len(blobs) > 5
    for s in NEVER:
        assert all(s not in b for b in blobs), s
    notes = {p.name: p.read_text() for p in files if p.suffix == ".md" and "raw/telemetry" in str(p)}
    log_note = next(n for n in notes.values() if 'kind: "log"' in n)
    for note in (notes["prod-sentry-s-101.md"], log_note):
        msg = [l for l in note.splitlines() if l.startswith("message:")][0]
        assert GUID in msg and APP in msg and "Ticket " in msg


def test_log_group_shows_real_scope_and_message(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    scope = "Shop.Plugins.VendorAccountSuitabilitySubmissionFetchXML"
    row = dict(LOG_ROW, service="worker", scope=scope, event_id="9908", message=f"Ticket {GUID} failed")
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [row])
    assert telemetry_run.main([], v, NOW) == 0
    [note] = [p.read_text() for p in (v / "raw/telemetry").glob("prod-adx-a-*.md")]
    assert f'exception: "{scope}#9908"' in note and "high_entropy" not in note
    assert f'message: "Ticket {GUID} failed"' in note


def test_sentry_title_becomes_the_message(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    title = f"InvalidOperationException: ticket {GUID} for {APP}"
    monkeypatch.setattr(sentry, "issues", lambda *a: [dict(_sentry_issue(101), title=title)])
    assert telemetry_run.main([], v, NOW) == 0
    assert f'message: "{title}"' in (v / "raw/telemetry/prod-sentry-s-101.md").read_text()
```

Replace `system/tests/fixtures/telemetry/kusto-logs.json` with:

```json
[{"FrameType":"DataSetHeader"},
 {"FrameType":"DataTable","TableKind":"PrimaryResult",
  "Columns":[{"ColumnName":"service"},{"ColumnName":"scope"},{"ColumnName":"event_id"},{"ColumnName":"n"},{"ColumnName":"first_ts"},{"ColumnName":"last_ts"},{"ColumnName":"traces"},{"ColumnName":"sample_trace"},{"ColumnName":"message"}],
  "Rows":[["api","Shop.Orders","4012",3,"2026-10-05T10:00:00Z","2026-10-05T11:00:00Z",2,"0af7651916cd43dd8448eb211c80319c","Ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b failed for bob@example.com password=hunter2"]]},
 {"FrameType":"DataSetCompletion","HasErrors":false}]
```

In `system/tests/telemetry.bats`, add after the first test:

```bash
@test "a log note keeps the ticket GUID in its message and masks the email and password" {
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 0 ]
  note=$(find "$V/raw/telemetry" -name 'prod-adx-a-*.md')
  grep -qF 'message: "Ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b failed for <email> password=[REDACTED:assignment]"' "$note"
  run grep -rlE 'bob@example.com|hunter2' "$V/raw/telemetry" "$V/system/logs"
  [ "$status" -ne 0 ]
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest system/tests/python/test_sentry.py system/tests/python/test_telemetry_run.py -q && bats system/tests/telemetry.bats`
Expected: FAIL. `KeyError: 'title'` in `test_issues_keep_only_allowed_fields_and_follow_cursor`; `IndexError` (no `message:` line) in `test_privacy_end_to_end`; `test_log_group_shows_real_scope_and_message` and `test_sentry_title_becomes_the_message` fail on their `message:` assertions; the new bats test fails on `grep -qF`.

- [ ] **Step 3: Implement**

In `system/scripts/vaultlib/sentry.py`, replace the docstring (`:1`) and `KEEP` (`:12-13`):

```python
"""Sentry REST client for the telemetry fetch (Plan 11 spec §2.2, §3.2). Keeps the issue fields notes use, title included."""
```

```python
KEEP = ("id", "shortId", "permalink", "project", "level", "status", "substatus", "firstSeen", "lastSeen",
        "count", "userCount", "type", "culprit", "environment", "title")
```

`_slim` already copies every `KEEP` key present in the issue, so `title` comes through; `metadata.value` and other tags are still dropped.

In `system/scripts/vaultlib/telemetry_run.py`, in the `groups.append({...})` call of `_adx_groups`, add after `"exception": exception,`:

```python
                           "message": r.get("message"),
```

Span rows have no `message` column, so span groups get `None` and the store writes no `message` line.

In `_sentry_groups`, add to the appended dict, after the `"exception": …` entry:

```python
                    "message": i.get("title"),
```

The message stays raw in memory; `Store._clean` masks it before anything is written, and `--dry-run` prints only `source`, `fingerprint`, `kind`, `service`, `exception` and `count`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest system/tests/python -q && bats system/tests/telemetry.bats`
Expected: 703 passed (681 before this plan), and 6 bats tests ok.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/sentry.py system/scripts/vaultlib/telemetry_run.py system/tests/fixtures/telemetry/kusto-logs.json system/tests/telemetry.bats system/tests/python/test_sentry.py system/tests/python/test_telemetry_run.py
git commit -m "feat(telemetry): notes carry the Sentry title and a sample log message"
```

### Task 5: Spec and README follow the new data policy

**Files:**
- Modify: `docs/superpowers/specs/2026-10-05-error-monitoring-design.md:4`, `:18`, `:85`, `:89`, `:91`, `:94`, `:125`, `:189`, `:192`
- Modify: `README.md:35`, `:95`, `:279`
- Test: `system/tests/python/test_telemetry_core.py` (a doc guard)

**Interfaces:**
- Consumes: the behavior of Tasks 1-4.
- Produces: documentation only.

- [ ] **Step 1: Write the failing test**

Append to `system/tests/python/test_telemetry_core.py`:

```python
def test_docs_state_the_identifier_policy():
    from helpers import REPO
    spec = (REPO / "docs/superpowers/specs/2026-10-05-error-monitoring-design.md").read_text()
    readme = (REPO / "README.md").read_text()
    assert "**Aggregates only.**" not in spec and "Identifiers kept, credentials masked" in spec
    assert "aggregate-only" not in readme and "no message text, titles or attribute values" not in readme
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest system/tests/python/test_telemetry_core.py::test_docs_state_the_identifier_policy -q`
Expected: FAIL on the first assertion.

- [ ] **Step 3: Edit the spec and README**

In the spec, after the `**Status:**` line (`:4`), add:

```markdown
**Revised:** 2026-10-07: data policy (identifiers kept, credentials and emails masked); `docs/superpowers/plans/2026-10-07-telemetry-identifiers.md`
```

Replace the Data policy row (`:18`) with:

```markdown
| Data policy | **Identifiers kept, credentials masked** (revised 2026-10-07; "aggregates only" is dropped for every source and environment). Notes hold group keys, counts, times, opaque IDs, links and one `message`: the Sentry issue `title`, or one sample `Body` per ADX log group, ticket identifiers (GUIDs, application IDs) included. Free text passes through `redact_credentials` (named token patterns, bearer tokens, URL passwords, connection-string keys, JSON secret fields, `password=`-style assignments) and emails become `<email>`; nothing else is masked. Group keys keep their shape (`<guid>`, `<n>`, `<hex>`, query strings dropped) so one group covers many tickets. State and the run log hold no free text. |
```

In §3.2 (`:85`), replace the sentence `` `title`, `metadata.value` and every tag value except `environment` are dropped at parse time and never written. `` with:

```markdown
`title` is kept and written as the note's `message` (masked as in §1, folded to one line, at most 500 characters); `metadata.value` and every tag value except `environment` are dropped at parse time.
```

In §3.3, replace `so only group keys and aggregates leave the cluster` (`:89`) with `so only group keys, aggregates and one sample message per log group leave the cluster`. At the end of the Logs bullet (`:91`), add:

```markdown
It also returns `message = take_any(body)` (`body = tostring(Body)`), outside the grouping.
```

At the end of the Fingerprint sentence (`:94`), add:

```markdown
The fingerprint hashes the keys as notes show them (`sanitize`: credentials and emails masked, IDs collapsed to their shape). Since 2026-10-07 key cleaning skips the generic high-entropy guess, which had merged long GUID-bearing routes and long type names into one `[REDACTED:high_entropy]` group; those groups split into their real errors, and their old notes stop updating and resolve after 7 quiet days. Every other fingerprint is unchanged.
```

In the §4 table, add after the `exception` row (`:125`):

```markdown
| new `message` | issue `title` | logs: one sample `Body`; spans: absent |
```

In §8, replace the privacy test sentence (`:189`, from `A **privacy test**` to the end of that bullet) with:

```markdown
A **privacy test** feeds Sentry issues and ADX rows whose fields hold credentials (an AWS key, bearer tokens, `password=`, SQL and Azure Storage connection strings, a URL password, a SAS `sig=`, a JSON `"password"` field), plain and URL-encoded emails, a ticket GUID and an application ID, and asserts that no credential or email appears in any note, the state file, the run log or the dry-run output, and that the GUID, the application ID and the title text do appear in the notes.
```

In the live acceptance bullet (`:192`), replace `for the forbidden patterns (GUIDs, URLs with query strings, emails)` with `for credentials and emails`.

In `README.md`:

- `:35`: in the 11a row, replace

  ```markdown
  ADX error groups into aggregate-only `production_error` notes;
  ```

  with

  ```markdown
  ADX error groups into `production_error` notes (credentials and emails masked);
  ```

- `:95`: replace `holding only group keys, counts, times, opaque IDs and links: no message text, titles or attribute values.` with `holding group keys, counts, times, opaque IDs, links and the Sentry issue title or one sample log message, ticket identifiers included; credentials and emails are masked.`
- `:279`: replace `Sentry and ADX responses are reduced to aggregates before anything is written: group keys are cleaned (GUIDs, emails, long hex and digit runs, URL query strings), and the note store re-checks every field.` with `Sentry and ADX responses are reduced to group keys, counts and one title or sample message before anything is written. Group keys keep their shape (GUIDs, emails, long hex and digit runs, URL query strings collapsed); titles and messages keep ticket identifiers with credentials and emails masked; the note store re-checks every field.`

- [ ] **Step 4: Run the full suites**

Run: `python3 -m pytest system/tests/python -q && bats system/tests/telemetry.bats`
Expected: 704 passed, and 6 bats tests ok.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-10-05-error-monitoring-design.md README.md system/tests/python/test_telemetry_core.py
git commit -m "docs(telemetry): data policy keeps identifiers, masks credentials and emails"
```

---

## Fix pass (review, 2026-10-08)

The template stays free of any one vault's specifics. The tests and this plan used names from a real codebase, its telemetry notes and an application ID; they now use generic stand-ins (`Acme.*` namespaces, `shop-*-adx` sources, `app.partition`/`app.slice`, `api/vendor/agent-credentials/…`, `A1-23B4C-D-56`). The note names the tests pin were recomputed by running the same generic rows through the code before and after Task 2: the six stable names are identical on both, and the two marker names (`shop-prod-adx-a-8513424e6ee9`, `shop-uat-adx-a-2f59495da85c`) appear only on the old code. Telemetry suites: 103 passed; `telemetry.bats`: 6 ok.
