# Plan 11: Error Monitoring from Sentry and ADX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An hourly, model-free fetch turns Sentry issues and Azure Data Explorer error groups into aggregate-only `production_error` notes in `raw/telemetry/`, which the morning brief lists and the Workcell with `telemetry` triages.

**Architecture:**
- Two stdlib HTTP clients (`vaultlib/kusto.py`, `vaultlib/sentry.py`) behind one injectable transport, so every test runs offline.
- Pure functions in `vaultlib/telemetry.py` (sources, windows, KQL, fingerprints, sanitizing); persistence in `vaultlib/telemetry_store.py` (state, notes, rebuild); orchestration in `vaultlib/telemetry_run.py`; the CLI is `system/scripts/telemetry_fetch.py`.
- A `foundry-telemetry` timer (standalone and server, only when a source is enabled), one call in `brief_prep.sh`, and wording changes to `/brief`, `/debrief`, `/setup` and the Maintenance Workcell.

**Tech Stack:** Python 3.11 stdlib (`urllib`, `hashlib`, `fcntl`, `json`), PyYAML through `vaultlib.yamlload`, bash 5, bats ≥ 1.8, pytest, systemd user units, Azure CLI (optional).

**Spec:** `docs/superpowers/specs/2026-10-05-error-monitoring-design.md` (Plan 11). Executors read both documents.

## Global Constraints

- **Data policy (spec §1):** notes, state and run log hold only group keys (sanitized), counts, times, opaque IDs (Sentry issue ID and short ID, one sample trace ID) and links. Never a Sentry `title` or `metadata.value`, a log `Body`, or any other attribute value.
- **No model, no network in headless runs (spec §1):** nothing here calls `claude`; `system/headless.settings.json` is unchanged.
- **Template rule:** no organization, cluster, project, hostname or instance ID is committed. Fixtures use `example`, `acme`, `https://example.kusto.windows.net`, `https://sentry.example.com`. American English.
- **Values are strings:** every frontmatter scalar is written and read as a string (`vaultlib.yamlload`); ints and bools are quoted (`count: "17"`, `covered: "true"`).
- **Sources:** `system/telemetry/<name>.md`, schema `telemetry_source` (spec §2.1). Names match `^[A-Za-z0-9._-]+$`.
- **Token file:** `${FOUNDRY_SENTRY_TOKEN_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/foundry/sentry.token}`; refused when `mode & 0o077`.
- **Limits:** ADX lag 10 min, Sentry lag 2 min, first window 24 h, window cap 7 days, 500 groups per ADX query, 5 pages × 100 Sentry issues, 20 coverage lookups and 20 Sentry status checks per run, 60 s per HTTP request, lock wait 120 s, resolve after 7 quiet days, alert after 3 consecutive failed runs, alerts at most once a day per source and kind.
- **Exit codes (`telemetry_fetch.py`):** 0 all sources ok (or none enabled); 1 at least one source failed; 2 usage; 4 lock busy.
- **Tool floor:** jq 1.6, bats 1.8 (no `run -N`), Python 3.11. bats ruling R1: no mid-test `!`, no `&&` assertion chains, no wall-clock timing assertions. `systemctl` is always a stub; tests use temp dirs.
- **Gate:** `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"`, then `sed -n '/===== summary/,$p' system/logs/gate.log`. **Lint:** `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log` (0 errors). Read verdicts from exit codes.
- **Never** run `install_units.sh`, `install_hooks.sh` or `/setup` against the real user session during tasks; live acceptance (Task 9) uses the real server only after the user says so.

## Decisions made while planning

- **D1 Module layout.** The spec's `kusto_query.py` and `sentry_api.py` become `vaultlib/kusto.py` and `vaultlib/sentry.py` (the repo keeps logic in `vaultlib/` behind thin scripts). Plan 11 ships no standalone query CLI; D (`/logs`) adds one.
- **D2 One transport seam.** Both clients call `http.request(method, url, headers, body) -> (status, bytes)`. Tests replace it in-process (pytest) or through `FOUNDRY_TELEMETRY_STUB=<dir>` (bats), which serves fixture files by route (Task 3). `az` is stubbed on `PATH` in bats and through `kusto.TOKEN_CMD` in pytest.
- **D3 Sanitizing group keys.** Group keys are attribute values by necessity (service, route, scope). `telemetry.sanitize()` runs `redact()` and replaces GUIDs, digit runs of 4+, emails and URL query strings with placeholders before any free-text key is fingerprinted or written, so `GET /items/1234` and `GET /items/5678` are one group. Two keys are validated instead of sanitized, because sanitizing would destroy them: a logger EventId must be a plain integer (`event_id()`), and a sample trace ID must be 16–32 hex digits (`trace_id()`, else dropped).
- **D4 Sentry `operation_id`** is the issue ID. The spec allows the latest event's trace ID "when present"; fetching it costs one call per issue for no triage value, so it is left out (YAGNI). Coverage (§3.4) works in the other direction and is unaffected.
- **D5 Sentry resolution.** Active Sentry groups not returned in a run are checked one by one (`GET …/issues/<id>/`), at most 20 per run, oldest `last_seen` first; `status: resolved` in Sentry resolves the note.
- **D6 Source list for units.** `telemetry_fetch.py --list` prints enabled source names; `install_units.sh` adds the telemetry units only when it prints one.

## Review Focus

1. **A Sentry issue or ADX row whose dropped fields hold GUIDs, URLs with SAS query strings, emails and free text.** Expected: none of those strings in any note, the state file or the run log. Pinned by the privacy test (Task 5, Step 1).
2. **The network fails mid-run after some notes were written.** Expected: the checkpoint does not advance, the next run rewrites the same groups without duplicates or double counting for Sentry, and ADX counts are not double-added. Pinned by "a failed source keeps its checkpoint and does not double count" (Task 6).
3. **The state file is deleted or corrupt while notes exist.** Expected: quarantined, rebuilt from notes, no duplicate notes. Pinned by the rebuild test (Task 5).
4. **The timer and `brief_prep.sh` start together.** Expected: one waits, the other exits 4 after 120 s; brief prep records "a fetch was already running". Pinned by the lock test (Task 6) and the prep test (Task 8).
5. **A source file with mixed-kind fields, a `covers` pointing at a disabled or other-environment source, or an unknown codebase.** Expected: lint errors naming the field; the fetch skips that source with an error line. Pinned by Task 2's lint tests.

---

### Task 1: Verify Sentry carries the trace ID (spike, no code)

**Files:**
- Create: `docs/superpowers/spikes/2026-10-05-plan-11-trace-coverage.md`

- [ ] **Step 1:** With the user's Sentry token (or the Sentry connector in an interactive session), take one recent ADX error-log `TraceID` from the first configured codebase's production database and query Sentry: `GET <sentry_url>/api/0/organizations/<org>/events/?dataset=errors&field=issue&field=issue.id&field=trace&query=trace:<TraceID>&statsPeriod=14d&per_page=1`.
- [ ] **Step 2:** Also list five recent Sentry error events with `field=trace` and confirm the `trace` column is populated.
- [ ] **Step 3:** Record the result in the spike note **without** any organization, project, cluster or ID: "Sentry error events carry the OpenTelemetry trace ID: yes/no; a trace query returns the issue: yes/no; endpoint and fields used". If either answer is no, Task 6 still ships `covers`, and its "coverage unavailable" path becomes the expected live behavior (spec §3.4).
- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/spikes/2026-10-05-plan-11-trace-coverage.md
git commit -m "docs(spike): Sentry trace-ID coverage check for Plan 11"
```

---

### Task 2: Schemas, source files and lint rules

**Files:**
- Create: `system/schemas/telemetry_source.md`, `system/telemetry/example.md`, `system/templates/production-error.md`
- Modify: `system/schemas/production_error.md`, `system/scripts/vaultlib/index.py` (`_global_issues`), `.gitignore`
- Test: `system/tests/python/test_telemetry_schema.py`

**Interfaces:**
- Produces: schema `telemetry_source` (fields below); extended `production_error`; global lint codes `telemetry-source` (error); `.gitignore` entries.

- [ ] **Step 1: Write the failing tests**

```python
# system/tests/python/test_telemetry_schema.py
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest system/tests/python/test_telemetry_schema.py -q`
Expected: FAIL (`unknown-type` for `telemetry_source`, unknown fields on `production_error`).

- [ ] **Step 3: Write the schema notes, example and template**

`system/schemas/telemetry_source.md`:

```markdown
---
type: schema
schema_for: telemetry_source
folders: ["system/telemetry/"]
fields:
  type: {kind: const, value: telemetry_source, required: true}
  name: {kind: string, required: true}
  codebase: {kind: string, required: true}
  environment: {kind: string, required: true}
  kind: {kind: enum, values: [sentry, adx], required: true}
  enabled: {kind: bool, default: "true"}
  rank: {kind: int, default: "50", min: "0", max: "999"}
  sentry_url: {kind: string}
  sentry_org: {kind: string}
  sentry_projects: {kind: list, of: string}
  sentry_query: {kind: string, default: "is:unresolved level:[error,fatal]"}
  adx_cluster: {kind: string}
  adx_database: {kind: string}
  adx_filter: {kind: map, of: string}
  adx_signals: {kind: list, of: {kind: enum, values: [logs, spans]}}
  adx_group_keys: {kind: list, of: string}
  covers: {kind: string}
---
# Telemetry source
One error source for a registered codebase (Plan 11 spec §2.1): a set of Sentry projects or one ADX database with a filter. Written by `/setup` phase 6a; gitignored except `example.md`. The linter checks the cross-field rules: only the fields of its `kind`, `name` equal to the file name, an existing `codebase`, and `covers` naming an enabled `sentry` source with the same `environment`.
```

Modify `system/schemas/production_error.md` (keep existing fields, add these, and update the body sentence):

```markdown
  environment: {kind: string}
  source: {kind: string}
  kind: {kind: enum, values: [sentry, log, span]}
  fingerprint: {kind: string}
  count: {kind: int, min: "0"}
  last_seen: {kind: datetime}
  status: {kind: enum, values: [active, resolved, deprecated], default: active}
  resolved_at: {kind: datetime}
  substatus: {kind: string}
  regressed: {kind: bool, default: "false"}
  sentry_issue: {kind: string}
  covered: {kind: bool, default: "false"}
  culprit: {kind: string}
  link: {kind: string}
```

Body: `A production error group in raw/telemetry/, written by telemetry_fetch.py (Plan 11) or dropped by hand (mock). Routed to the Workcell with telemetry; never ingested. Aggregates only: no message text or attribute values.`

`system/telemetry/example.md`:

```markdown
---
type: telemetry_source
name: "example"
codebase: "example"
environment: "prod"
kind: "adx"
enabled: "false"
adx_cluster: "https://example.westus.kusto.windows.net"
adx_database: "production"
adx_filter: {}
---
An example ADX source. `/setup` phase 6a writes real ones next to it (gitignored). A Sentry source sets `kind: "sentry"`, `sentry_url`, `sentry_org` and `sentry_projects` instead of the `adx_*` fields.
```

`system/templates/production-error.md` (placeholders filled by `telemetry_store.render_body`; not a note):

```markdown
# {{exception}} ({{environment}})

| Key | Value |
|---|---|
{{key_rows}}

| Count | First seen | Last seen | Status |
|---|---|---|---|
| {{count}} | {{detected_at}} | {{last_seen}} | {{status}} |

{{reopen}}
```

`.gitignore` additions:

```
system/telemetry/*.md
!system/telemetry/example.md
system/telemetry.lock
```

- [ ] **Step 4: Add the cross-field rules to the index**

In `vaultlib/index.py`, call `self._telemetry_source_issues(conn, add)` from `_global_issues` right after `self._supersession_issues(conn, add)`, and add:

```python
    SENTRY_FIELDS = ("sentry_url", "sentry_org", "sentry_projects", "sentry_query")
    ADX_FIELDS = ("adx_cluster", "adx_database", "adx_filter", "adx_signals", "adx_group_keys", "covers")

    def _telemetry_source_issues(self, conn, add):
        """Cross-field rules for telemetry_source notes (Plan 11 spec §2.1)."""
        def field(path, key):
            row = conn.execute("SELECT value FROM fields WHERE path=? AND key=?", (path, key)).fetchone()
            return row[0] if row else None

        def has(path, key):
            return conn.execute("SELECT 1 FROM fields WHERE path=? AND (key=? OR key LIKE ?)",
                                (path, key, key + ".%")).fetchone() is not None

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
            other = self.ADX_FIELDS if kind == "sentry" else self.SENTRY_FIELDS
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
```

Check before writing it: how `fields` stores list and map values (run `system/scripts/vault_index.py query "SELECT key, value FROM fields WHERE path='system/codebases/example.md'"` on a scratch vault). If lists are stored under `key` with JSON text rather than `key.N`, `has()` already matches by the exact key; keep both branches.

- [ ] **Step 5: Run the tests and the schema-note suite**

Run: `python3 -m pytest system/tests/python/test_telemetry_schema.py system/tests/python/test_schema_notes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add system/schemas/telemetry_source.md system/schemas/production_error.md system/telemetry/example.md \
  system/templates/production-error.md system/scripts/vaultlib/index.py .gitignore system/tests/python/test_telemetry_schema.py
git commit -m "feat(telemetry): telemetry_source schema, extended production_error, cross-field lint"
```

---

### Task 3: HTTP transport, the stub, and the Kusto client

**Files:**
- Create: `system/scripts/vaultlib/http.py`, `system/scripts/vaultlib/kusto.py`
- Test: `system/tests/python/test_kusto.py`

**Interfaces:**
- Produces:
  - `http.TelemetryError(Exception)` with `.kind in {"auth", "transient", "bad"}` and `.reason: str` (short, no response body).
  - `http.request(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]`; honours `FOUNDRY_TELEMETRY_STUB`.
  - `http.json_call(method, url, headers, body=None) -> tuple[object, dict]` returning parsed JSON and response headers; raises `TelemetryError` (401/403 → auth, 429/5xx/timeouts/URLError → transient, other 4xx and bad JSON → bad).
  - `kusto.token(cluster: str) -> str` via `kusto.TOKEN_CMD` (default `["az", "account", "get-access-token", "--resource", <cluster>, "--query", "accessToken", "-o", "tsv"]`); missing `az` or non-zero exit → `TelemetryError("auth", "run az login")`.
  - `kusto.query(cluster: str, database: str, kql: str, max_rows: int = 500) -> list[dict]`; refuses KQL starting with `.` (`TelemetryError("bad", …)`).

- [ ] **Step 1: Write the failing tests**

```python
# system/tests/python/test_kusto.py
import json

import pytest

from vaultlib import http, kusto

V2 = [
    {"FrameType": "DataSetHeader"},
    {"FrameType": "DataTable", "TableKind": "QueryProperties", "Columns": [], "Rows": []},
    {"FrameType": "DataTable", "TableKind": "PrimaryResult",
     "Columns": [{"ColumnName": "service"}, {"ColumnName": "n"}], "Rows": [["api", 3], ["worker", 1]]},
    {"FrameType": "DataSetCompletion", "HasErrors": False},
]


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(method, url, headers, body):
        seen.append((method, url, headers, json.loads(body) if body else None))
        return 200, json.dumps(V2).encode()

    monkeypatch.setattr(http, "request", fake)
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    return seen


def test_query_returns_primary_rows_as_dicts(calls):
    rows = kusto.query("https://example.kusto.windows.net", "prod", "Logs | take 1")
    assert rows == [{"service": "api", "n": 3}, {"service": "worker", "n": 1}]
    method, url, headers, body = calls[0]
    assert url == "https://example.kusto.windows.net/v2/rest/query"
    assert headers["Authorization"] == "Bearer tok"
    assert body["db"] == "prod" and body["properties"]["Options"]["request_readonly"] is True


@pytest.mark.parametrize("kql", [".show tables", "  .drop table Logs", "\n.set-or-append x <| print 1"])
def test_management_commands_are_refused(calls, kql):
    with pytest.raises(http.TelemetryError) as exc:
        kusto.query("https://example.kusto.windows.net", "prod", kql)
    assert exc.value.kind == "bad"
    assert calls == []


def test_status_mapping(monkeypatch):
    monkeypatch.setattr(kusto, "token", lambda cluster: "tok")
    for status, kind in ((401, "auth"), (403, "auth"), (429, "transient"), (503, "transient"), (400, "bad")):
        monkeypatch.setattr(http, "request", lambda *a, s=status: (s, b'{"error":{"message":"secret detail"}}'))
        with pytest.raises(http.TelemetryError) as exc:
            kusto.query("https://example.kusto.windows.net", "prod", "print 1")
        assert exc.value.kind == kind
        assert "secret detail" not in exc.value.reason


def test_missing_az_is_an_auth_error(monkeypatch):
    monkeypatch.setattr(kusto, "TOKEN_CMD", ["/nonexistent/az"])
    with pytest.raises(http.TelemetryError) as exc:
        kusto.token("https://example.kusto.windows.net")
    assert exc.value.kind == "auth"


def test_stub_directory_serves_fixtures_by_route(tmp_path, monkeypatch):
    (tmp_path / "kusto-logs.json").write_text(json.dumps(V2))
    monkeypatch.setenv("FOUNDRY_TELEMETRY_STUB", str(tmp_path))
    status, body = http.request("POST", "https://example.kusto.windows.net/v2/rest/query", {},
                                json.dumps({"csl": "Logs | where x"}).encode())
    assert status == 200 and json.loads(body) == V2
    (tmp_path / "kusto-spans.status").write_text("503")
    status, _ = http.request("POST", "https://example.kusto.windows.net/v2/rest/query", {},
                             json.dumps({"csl": "Traces | where x"}).encode())
    assert status == 503
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest system/tests/python/test_kusto.py -q`
Expected: FAIL (`ModuleNotFoundError: vaultlib.http`).

- [ ] **Step 3: Implement `vaultlib/http.py`**

```python
"""HTTP for the telemetry clients (Plan 11 spec §3): one seam, stub-able by FOUNDRY_TELEMETRY_STUB."""
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 60


class TelemetryError(Exception):
    def __init__(self, kind: str, reason: str):
        super().__init__(f"{kind}: {reason}")
        self.kind, self.reason = kind, reason


def _route(url: str, body: bytes | None) -> str:
    """Stub route for a request: kusto-logs|kusto-spans|kusto-count|kusto-check|sentry-projects|sentry-issues|sentry-issue|sentry-trace."""
    if "/v2/rest/query" in url:
        csl = json.loads(body or b"{}").get("csl", "").lstrip()
        if csl.startswith("print"):
            return "kusto-check"
        if "| count" in csl:
            return "kusto-count"
        return "kusto-logs" if csl.startswith("Logs") else "kusto-spans"
    if "/events/" in url:
        return "sentry-trace"
    if "/projects/" in url:
        return "sentry-projects"
    if url.rstrip("/").split("?")[0].split("/")[-1].isdigit():
        return "sentry-issue"
    return "sentry-issues"


def _stub(stub_dir: str, url: str, body: bytes | None) -> tuple[int, bytes]:
    route = _route(url, body)
    d = Path(stub_dir)
    with open(d / "requests.log", "a", encoding="utf-8") as log:
        log.write(f"{route} {url}\n")
    status = int((d / f"{route}.status").read_text().strip()) if (d / f"{route}.status").exists() else 200
    data = (d / f"{route}.json").read_bytes() if (d / f"{route}.json").exists() else b"[]"
    return status, data


def request(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
    stub = os.environ.get("FOUNDRY_TELEMETRY_STUB")
    if stub:
        return _stub(stub, url, body)
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            request.last_headers = dict(resp.headers)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        request.last_headers = dict(exc.headers or {})
        return exc.code, b""
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise TelemetryError("transient", f"network: {type(exc).__name__}") from None


request.last_headers = {}


def json_call(method: str, url: str, headers: dict, body: bytes | None = None):
    status, data = request(method, url, headers, body)
    if status in (401, 403):
        raise TelemetryError("auth", f"HTTP {status}")
    if status == 429 or status >= 500:
        raise TelemetryError("transient", f"HTTP {status}")
    if status >= 400:
        raise TelemetryError("bad", f"HTTP {status}")
    try:
        return json.loads(data or b"null"), getattr(request, "last_headers", {})
    except ValueError:
        raise TelemetryError("bad", "response is not JSON") from None
```

- [ ] **Step 4: Implement `vaultlib/kusto.py`**

```python
"""Read-only ADX queries over the v2 REST API (Plan 11 spec §3)."""
import json
import subprocess

from . import http
from .http import TelemetryError

TOKEN_CMD = ["az"]


def token(cluster: str) -> str:
    cmd = TOKEN_CMD + (["account", "get-access-token", "--resource", cluster, "--query", "accessToken", "-o", "tsv"]
                       if TOKEN_CMD == ["az"] else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, PermissionError):
        raise TelemetryError("auth", "az is not installed; install the Azure CLI and run az login") from None
    except subprocess.TimeoutExpired:
        raise TelemetryError("transient", "az timed out") from None
    tok = out.stdout.strip()
    if out.returncode != 0 or not tok:
        raise TelemetryError("auth", "run az login")
    return tok


def query(cluster: str, database: str, kql: str, max_rows: int = 500) -> list[dict]:
    if kql.lstrip().startswith("."):
        raise TelemetryError("bad", "management commands are not allowed")
    body = json.dumps({"db": database, "csl": kql, "properties": {"Options": {
        "request_readonly": True, "servertimeout": "00:01:00", "truncationmaxrecords": max_rows}}}).encode()
    headers = {"Authorization": f"Bearer {token(cluster)}", "Content-Type": "application/json",
               "Accept": "application/json"}
    frames, _ = http.json_call("POST", cluster.rstrip("/") + "/v2/rest/query", headers, body)
    for frame in frames if isinstance(frames, list) else []:
        if frame.get("FrameType") == "DataTable" and frame.get("TableKind") == "PrimaryResult":
            cols = [c["ColumnName"] for c in frame.get("Columns", [])]
            return [dict(zip(cols, row)) for row in frame.get("Rows", [])][:max_rows]
        if frame.get("FrameType") == "DataSetCompletion" and frame.get("HasErrors"):
            raise TelemetryError("bad", "query reported errors")
    raise TelemetryError("bad", "no primary result")
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest system/tests/python/test_kusto.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add system/scripts/vaultlib/http.py system/scripts/vaultlib/kusto.py system/tests/python/test_kusto.py
git commit -m "feat(telemetry): HTTP seam with fixture stub and read-only Kusto client"
```

---

### Task 4: Sentry client

**Files:**
- Create: `system/scripts/vaultlib/sentry.py`
- Test: `system/tests/python/test_sentry.py`

**Interfaces:**
- Consumes: `http.json_call`, `http.TelemetryError`.
- Produces:
  - `sentry.token() -> str` (reads the token file; mode check; missing/too open → `TelemetryError("auth", <path and fix>)`).
  - `sentry.project_ids(base: str, org: str, slugs: list[str]) -> dict[str, str]` (slug → id; unknown slug → `TelemetryError("bad", "unknown project <slug>")`).
  - `sentry.issues(base, org, project_ids: list[str], query: str, since: datetime) -> list[dict]`; each dict holds only `KEEP` keys (below), at most 5 pages.
  - `sentry.issue_status(base, org, issue_id) -> str` (`resolved`, `unresolved`, `ignored`).
  - `sentry.issue_for_trace(base, org, trace_id) -> dict | None` (`{"id", "shortId"}`).
  - `sentry.KEEP = ("id", "shortId", "permalink", "project", "level", "status", "substatus", "firstSeen", "lastSeen", "count", "userCount", "type", "culprit", "environment")`.

- [ ] **Step 1: Write the failing tests**

```python
# system/tests/python/test_sentry.py
import json
import os
from datetime import datetime, timezone

import pytest

from vaultlib import http, sentry

ISSUE = {"id": "101", "shortId": "API-1", "permalink": "https://sentry.example.com/organizations/acme/issues/101/",
         "project": {"slug": "api"}, "level": "error", "status": "unresolved", "substatus": "new",
         "firstSeen": "2026-10-05T10:00:00Z", "lastSeen": "2026-10-05T11:00:00Z", "count": "4", "userCount": 2,
         "title": "Failed for ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b", "culprit": "orders/Submit.cs in Submit",
         "metadata": {"type": "System.InvalidOperationException", "value": "user bob@example.com"},
         "tags": [{"key": "environment", "value": "api"}]}


@pytest.fixture
def token_file(tmp_path, monkeypatch):
    f = tmp_path / "sentry.token"
    f.write_text("sntrys_abc\n")
    os.chmod(f, 0o600)
    monkeypatch.setenv("FOUNDRY_SENTRY_TOKEN_FILE", str(f))
    return f


def test_token_refuses_group_readable_file(token_file):
    os.chmod(token_file, 0o644)
    with pytest.raises(http.TelemetryError) as exc:
        sentry.token()
    assert exc.value.kind == "auth" and "0600" in exc.value.reason


def test_issues_keep_only_allowed_fields_and_follow_cursor(token_file, monkeypatch):
    pages = [([ISSUE], {"Link": '<https://x/?cursor=0:100:0>; rel="next"; results="true"; cursor="0:100:0"'}),
             ([dict(ISSUE, id="102", shortId="API-2")], {"Link": '<https://x>; rel="next"; results="false"; cursor="0:200:0"'})]
    urls = []

    def fake(method, url, headers, body=None):
        urls.append(url)
        return pages[len(urls) - 1]

    monkeypatch.setattr(http, "json_call", fake)
    got = sentry.issues("https://sentry.example.com", "acme", ["7"], "is:unresolved",
                        datetime(2026, 10, 5, 9, tzinfo=timezone.utc))
    assert [g["shortId"] for g in got] == ["API-1", "API-2"]
    assert set(got[0]) <= set(sentry.KEEP)
    assert got[0]["type"] == "System.InvalidOperationException" and got[0]["environment"] == "api"
    assert "title" not in got[0] and "bob@example.com" not in json.dumps(got)
    assert "lastSeen%3A%3E%3D2026-10-05T09%3A00%3A00" in urls[0] and "project=7" in urls[0]
    assert "cursor=0%3A100%3A0" in urls[1]


def test_page_cap_is_five(token_file, monkeypatch):
    link = {"Link": '<https://x>; rel="next"; results="true"; cursor="c"'}
    monkeypatch.setattr(http, "json_call", lambda *a, **k: ([ISSUE], link))
    assert len(sentry.issues("https://sentry.example.com", "acme", ["7"], "", datetime.now(timezone.utc))) == 5


def test_issue_for_trace(token_file, monkeypatch):
    monkeypatch.setattr(http, "json_call", lambda *a, **k: ({"data": [{"issue": "API-1", "issue.id": 101}]}, {}))
    assert sentry.issue_for_trace("https://sentry.example.com", "acme", "abc") == {"id": "101", "shortId": "API-1"}
    monkeypatch.setattr(http, "json_call", lambda *a, **k: ({"data": []}, {}))
    assert sentry.issue_for_trace("https://sentry.example.com", "acme", "abc") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest system/tests/python/test_sentry.py -q`
Expected: FAIL (`ModuleNotFoundError: vaultlib.sentry`).

- [ ] **Step 3: Implement `vaultlib/sentry.py`**

```python
"""Sentry REST client for the telemetry fetch (Plan 11 spec §2.2, §3.2). Keeps only aggregate fields."""
import os
import re
import stat
import urllib.parse
from datetime import datetime
from pathlib import Path

from . import http
from .http import TelemetryError

KEEP = ("id", "shortId", "permalink", "project", "level", "status", "substatus", "firstSeen", "lastSeen",
        "count", "userCount", "type", "culprit", "environment")
MAX_PAGES = 5
NEXT = re.compile(r'<[^>]*>;\s*rel="next";\s*results="(true|false)";\s*cursor="([^"]*)"')


def token_path() -> Path:
    env = os.environ.get("FOUNDRY_SENTRY_TOKEN_FILE")
    if env:
        return Path(env)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "foundry" / "sentry.token"


def token() -> str:
    p = token_path()
    try:
        mode = p.stat().st_mode
    except FileNotFoundError:
        raise TelemetryError("auth", f"no Sentry token at {p}; create it with mode 0600") from None
    if stat.S_IMODE(mode) & 0o077:
        raise TelemetryError("auth", f"{p} is readable by others; chmod 0600 it")
    tok = p.read_text(encoding="utf-8").strip()
    if not tok:
        raise TelemetryError("auth", f"{p} is empty")
    return tok


def _get(base: str, path: str, params: list) -> tuple:
    url = base.rstrip("/") + path + ("?" + urllib.parse.urlencode(params) if params else "")
    return http.json_call("GET", url, {"Authorization": f"Bearer {token()}", "Accept": "application/json"})


def project_ids(base: str, org: str, slugs: list) -> dict:
    found, cursor = {}, None
    for _ in range(MAX_PAGES):
        data, headers = _get(base, f"/api/0/organizations/{org}/projects/", [("cursor", cursor)] if cursor else [])
        for p in data or []:
            if p.get("slug") in slugs:
                found[p["slug"]] = str(p["id"])
        m = NEXT.search(headers.get("Link", ""))
        if not m or m.group(1) != "true":
            break
        cursor = m.group(2)
    for s in slugs:
        if s not in found:
            raise TelemetryError("bad", f"unknown project {s}")
    return found


def _slim(issue: dict) -> dict:
    out = {k: issue.get(k) for k in KEEP if k in issue and k not in ("type", "environment", "project")}
    out["project"] = (issue.get("project") or {}).get("slug")
    out["type"] = (issue.get("metadata") or {}).get("type") or issue.get("type")
    env = [t.get("value") for t in issue.get("tags") or [] if t.get("key") == "environment"]
    out["environment"] = env[0] if env else None
    return out


def issues(base: str, org: str, project_ids_: list, query: str, since: datetime) -> list:
    q = f"{query} lastSeen:>={since.strftime('%Y-%m-%dT%H:%M:%S')}".strip()
    params = [("project", i) for i in project_ids_] + [("query", q), ("statsPeriod", "14d"), ("limit", "100")]
    out, cursor = [], None
    for _ in range(MAX_PAGES):
        data, headers = _get(base, f"/api/0/organizations/{org}/issues/", params + ([("cursor", cursor)] if cursor else []))
        out += [_slim(i) for i in data or []]
        m = NEXT.search(headers.get("Link", ""))
        if not m or m.group(1) != "true":
            break
        cursor = m.group(2)
    return out


def issue_status(base: str, org: str, issue_id: str) -> str:
    data, _ = _get(base, f"/api/0/organizations/{org}/issues/{issue_id}/", [])
    return str((data or {}).get("status", "unresolved"))


def issue_for_trace(base: str, org: str, trace_id: str) -> dict | None:
    data, _ = _get(base, f"/api/0/organizations/{org}/events/", [
        ("dataset", "errors"), ("field", "issue"), ("field", "issue.id"),
        ("query", f"trace:{trace_id}"), ("statsPeriod", "14d"), ("per_page", "1")])
    rows = (data or {}).get("data") or []
    if not rows:
        return None
    return {"id": str(rows[0].get("issue.id")), "shortId": str(rows[0].get("issue"))}
```

Adjust `issue_for_trace` to the endpoint and fields Task 1 recorded, if they differ.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest system/tests/python/test_sentry.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/vaultlib/sentry.py system/tests/python/test_sentry.py
git commit -m "feat(telemetry): Sentry client keeping aggregate fields only"
```

---

### Task 5: Pure core and the note store

**Files:**
- Create: `system/scripts/vaultlib/telemetry.py`, `system/scripts/vaultlib/telemetry_store.py`
- Test: `system/tests/python/test_telemetry_core.py`, `system/tests/python/test_telemetry_store.py`

**Interfaces:**
- Consumes: `frontmatter.parse`, `yamlload`, `redact.redact`.
- Produces (`telemetry.py`):
  - `Source` dataclass: `path, name, codebase, partition, environment, kind, enabled: bool, rank: int, sentry_url, sentry_org, sentry_projects: list, sentry_query, adx_cluster, adx_database, adx_filter: dict, adx_signals: list, adx_group_keys: list, covers`.
  - `load_sources(vault: Path) -> list[Source]` (skips `example.md`; sorted by `rank`, then `name`; `partition` from `system/codebases/<codebase>.md`, default `work`).
  - `window(checkpoint: str | None, now: datetime, kind: str) -> tuple[datetime, datetime, bool]` (`moved` true when the 7-day cap moved the start).
  - `kql_logs(src, start, end, limit=500) -> str`, `kql_spans(src, start, end, limit=500) -> str`, `kql_count(kql: str) -> str`.
  - `sanitize(value) -> str` for free-text keys (service, scope, route, extra keys); `event_id(value) -> str` keeps an integer EventId; `trace_id(value) -> str` keeps a hex trace ID or returns `""`.
  - `fingerprint(source: str, signal: str, keys: dict) -> str` → `a-<12 hex>`.
- Produces (`telemetry_store.py`):
  - `Store(vault: Path)` with `.state: dict`, `load() -> list[str]` (returns warnings, quarantines a corrupt file and rebuilds), `save()`, `upsert(group: dict, now: datetime) -> str` (`"new"|"updated"`), `resolve_stale(source: str, now: datetime) -> int`, `set_status(fingerprint, status, now)`, `active(source) -> list[dict]`.
  - Group dict keys: `fingerprint, source, environment, codebase, partition, kind, service, exception, operation_id, detected_at, last_seen, count, keys: dict, substatus?, sentry_issue?, covered?, culprit?, link?, reopen?`. For Sentry groups `count` replaces; for ADX groups `count` adds.

- [ ] **Step 1: Write the failing core tests**

```python
# system/tests/python/test_telemetry_core.py
from datetime import datetime, timedelta, timezone

from helpers import write
from vaultlib import telemetry as t

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def adx(**kw):
    base = dict(path="system/telemetry/p.md", name="p", codebase="shop", partition="work", environment="prod", kind="adx",
                enabled=True, rank=50, sentry_url=None, sentry_org=None, sentry_projects=[], sentry_query="",
                adx_cluster="https://example.kusto.windows.net", adx_database="prod", adx_filter={},
                adx_signals=["logs", "spans"], adx_group_keys=[], covers=None)
    base.update(kw)
    return t.Source(**base)


def test_window_first_run_cap_and_lag():
    s, e, moved = t.window(None, NOW, "adx")
    assert (s, e, moved) == (NOW - timedelta(hours=24), NOW - timedelta(minutes=10), False)
    s, e, moved = t.window((NOW - timedelta(days=30)).isoformat(), NOW, "sentry")
    assert s == NOW - timedelta(minutes=2) - timedelta(days=7) and moved is True
    s, e, _ = t.window((NOW - timedelta(hours=1)).isoformat(), NOW, "adx")
    assert s == NOW - timedelta(hours=1)


def test_kql_filter_and_group_keys_are_quoted():
    q = t.kql_logs(adx(adx_filter={"deployment.instance": 'u"at'}, adx_group_keys=["app.module"]),
                   NOW - timedelta(hours=1), NOW)
    assert q.startswith("Logs\n")
    assert 'tostring(ResourceAttributes["deployment.instance"]) == "u\\"at"' in q
    assert 'module_0 = tostring(LogsAttributes["app.module"])' in q
    assert "SeverityNumber >= 17" in q and "take 500" in q
    assert "Body" not in q
    s = t.kql_spans(adx(), NOW - timedelta(hours=1), NOW)
    assert s.startswith("Traces\n") and 'SpanKind == "SPAN_KIND_SERVER"' in s


def test_sanitize_and_fingerprint_collapse_ids():
    assert t.sanitize("GET /items/12345?sig=abc") == "GET /items/<n>"
    assert t.sanitize("ticket 3f2b8a1e-9c4d-4e1f-8a2b-1c3d4e5f6a7b by bob@example.com") == "ticket <guid> by <email>"
    a = t.fingerprint("p", "span", {"route": t.sanitize("GET /items/1234")})
    b = t.fingerprint("p", "span", {"route": t.sanitize("GET /items/5678")})
    assert a == b and a.startswith("a-") and len(a) == 14
    assert t.fingerprint("p", "span", {"x": "1", "y": "2"}) == t.fingerprint("p", "span", {"y": "2", "x": "1"})
    assert t.event_id("40123") == "40123" and t.event_id("id 12345678901") == "id <n>"
    assert t.trace_id("0af7651916cd43dd8448eb211c80319c") == "0af7651916cd43dd8448eb211c80319c"
    assert t.trace_id("not a trace") == ""


def test_load_sources_reads_partition_and_skips_example(vault):
    write(vault, "system/codebases/shop.md", '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "personal"\nsearch_globs: ["*"]\n---\n')
    write(vault, "system/telemetry/example.md", '---\ntype: telemetry_source\nname: "example"\n---\n')
    write(vault, "system/telemetry/b.md", '---\ntype: telemetry_source\nname: "b"\ncodebase: "shop"\nenvironment: "uat"\nkind: "adx"\nrank: "60"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n')
    write(vault, "system/telemetry/a.md", '---\ntype: telemetry_source\nname: "a"\ncodebase: "shop"\nenvironment: "prod"\nkind: "sentry"\nrank: "10"\nenabled: "false"\nsentry_url: "https://s"\nsentry_org: "o"\nsentry_projects: ["api"]\n---\n')
    got = t.load_sources(vault)
    assert [s.name for s in got] == ["a", "b"]
    assert got[1].partition == "personal" and got[0].enabled is False and got[1].adx_signals == ["logs", "spans"]
```

- [ ] **Step 2: Write the failing store tests (including the privacy test)**

```python
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
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m pytest system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_store.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Implement `vaultlib/telemetry.py`**

```python
"""Pure parts of the telemetry fetch (Plan 11 spec §2.1, §3.1, §3.3): sources, windows, KQL, keys."""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import frontmatter
from .redact import redact

LAG = {"adx": timedelta(minutes=10), "sentry": timedelta(minutes=2)}
FIRST = timedelta(hours=24)
CAP = timedelta(days=7)
GUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")
DIGITS = re.compile(r"\d{4,}")
QUERY = re.compile(r"\?\S*")


@dataclass
class Source:
    path: str
    name: str
    codebase: str
    partition: str
    environment: str
    kind: str
    enabled: bool = True
    rank: int = 50
    sentry_url: str | None = None
    sentry_org: str | None = None
    sentry_projects: list = field(default_factory=list)
    sentry_query: str = "is:unresolved level:[error,fatal]"
    adx_cluster: str | None = None
    adx_database: str | None = None
    adx_filter: dict = field(default_factory=dict)
    adx_signals: list = field(default_factory=lambda: ["logs", "spans"])
    adx_group_keys: list = field(default_factory=list)
    covers: str | None = None


def _fm(path: Path) -> dict:
    note = frontmatter.parse(path.read_text(encoding="utf-8"))
    return note.data or {}


def load_sources(vault: Path) -> list:
    vault = Path(vault)
    out = []
    for p in sorted((vault / "system" / "telemetry").glob("*.md")):
        if p.name == "example.md":
            continue
        d = _fm(p)
        if d.get("type") != "telemetry_source":
            continue
        cb = vault / "system" / "codebases" / f"{d.get('codebase', '')}.md"
        partition = (_fm(cb).get("partition") if cb.is_file() else None) or "work"
        out.append(Source(
            path=p.relative_to(vault).as_posix(), name=str(d.get("name", p.stem)), codebase=str(d.get("codebase", "")),
            partition=partition, environment=str(d.get("environment", "")), kind=str(d.get("kind", "")),
            enabled=str(d.get("enabled", "true")).lower() == "true", rank=int(d.get("rank", "50") or 50),
            sentry_url=d.get("sentry_url"), sentry_org=d.get("sentry_org"), sentry_projects=list(d.get("sentry_projects") or []),
            sentry_query=d.get("sentry_query") or "is:unresolved level:[error,fatal]",
            adx_cluster=d.get("adx_cluster"), adx_database=d.get("adx_database"), adx_filter=dict(d.get("adx_filter") or {}),
            adx_signals=list(d.get("adx_signals") or ["logs", "spans"]), adx_group_keys=list(d.get("adx_group_keys") or []),
            covers=d.get("covers")))
    return sorted(out, key=lambda s: (s.rank, s.name))


def window(checkpoint: str | None, now: datetime, kind: str):
    end = now - LAG[kind]
    start = datetime.fromisoformat(checkpoint) if checkpoint else now - FIRST
    moved = False
    if end - start > CAP:
        start, moved = end - CAP, True
    return start, end, moved


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _t(dt: datetime) -> str:
    return f"datetime({dt.strftime('%Y-%m-%dT%H:%M:%SZ')})"


def _filters(src: Source) -> list:
    return [f"| where tostring(ResourceAttributes[{_q(k)}]) == {_q(v)}" for k, v in sorted(src.adx_filter.items())]


def kql_logs(src: Source, start: datetime, end: datetime, limit: int = 500) -> str:
    extra = [f"module_{i} = tostring(LogsAttributes[{_q(k)}])" for i, k in enumerate(src.adx_group_keys)]
    by = ["service", "scope", "event_id"] + [f"module_{i}" for i in range(len(src.adx_group_keys))]
    return "\n".join(["Logs",
                      f"| where Timestamp >= {_t(start)} and Timestamp < {_t(end)} and SeverityNumber >= 17",
                      *_filters(src),
                      "| extend service = tostring(ResourceAttributes[\"service.name\"]), "
                      "scope = tostring(LogsAttributes[\"scope.name\"]), event_id = tostring(LogsAttributes[\"logrecord.event.id\"])"
                      + (", " + ", ".join(extra) if extra else ""),
                      f"| summarize n = count(), first = min(Timestamp), last = max(Timestamp), traces = dcount(TraceID), "
                      f"sample_trace = take_any(TraceID) by {', '.join(by)}",
                      f"| take {limit}"])


def kql_spans(src: Source, start: datetime, end: datetime, limit: int = 500) -> str:
    return "\n".join(["Traces",
                      f"| where StartTime >= {_t(start)} and StartTime < {_t(end)} and SpanKind == \"SPAN_KIND_SERVER\"",
                      *_filters(src),
                      "| extend status = toint(TraceAttributes[\"http.response.status_code\"])",
                      "| where SpanStatus == \"STATUS_CODE_ERROR\" or status >= 500",
                      "| extend service = tostring(ResourceAttributes[\"service.name\"]), "
                      "route = coalesce(tostring(TraceAttributes[\"http.route\"]), SpanName)",
                      "| summarize n = count(), first = min(StartTime), last = max(StartTime), traces = dcount(TraceID), "
                      "sample_trace = take_any(TraceID) by service, route, status",
                      f"| take {limit}"])


def kql_count(kql: str) -> str:
    """The group count of a logs or spans query: drop its take line and count."""
    return "\n".join(line for line in kql.split("\n") if not line.startswith("| take ")) + "\n| count"


def sanitize(value) -> str:
    text, _ = redact(str(value if value is not None else ""))
    text = QUERY.sub("", text)
    text = GUID.sub("<guid>", text)
    text = EMAIL.sub("<email>", text)
    text = DIGITS.sub("<n>", text)
    return text[:200]


def event_id(value) -> str:
    """A logger EventId is a code constant, the grouping key itself: keep a plain integer, sanitize anything else."""
    v = str(value if value is not None else "")
    return v if re.fullmatch(r"-?\d{1,9}", v) else sanitize(v)


def trace_id(value) -> str:
    """An opaque OpenTelemetry trace ID (hex); anything else is dropped."""
    v = str(value if value is not None else "")
    return v if re.fullmatch(r"[0-9a-fA-F]{16,32}", v) else ""


def fingerprint(source: str, signal: str, keys: dict) -> str:
    raw = "|".join([source, signal] + [f"{k}={keys[k]}" for k in sorted(keys)])
    return "a-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
```

Check: `vaultlib/redact.py`'s `redact()` signature returns `(text, count)` (see `system/scripts/redact.py`); the test expects `sanitize("GET /items/12345?sig=abc") == "GET /items/<n>"`.

- [ ] **Step 5: Implement `vaultlib/telemetry_store.py`**

```python
"""State and notes for the telemetry fetch (Plan 11 spec §3.5, §4, §5.1)."""
import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from . import frontmatter

STATE = "system/logs/telemetry_state.json"
QUIET = timedelta(days=7)
NOTE_FIELDS = ("type", "service", "exception", "operation_id", "detected_at", "codebase", "partition", "environment",
               "source", "kind", "fingerprint", "count", "last_seen", "status", "resolved_at", "substatus", "regressed",
               "sentry_issue", "covered", "culprit", "link")


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, vault: Path):
        self.vault = Path(vault)
        self.state = {"sources": {}, "groups": {}, "alerts": {}}

    def note_rel(self, source: str, fp: str) -> str:
        return f"raw/telemetry/{source}-{fp}.md"

    def load(self) -> list:
        p = self.vault / STATE
        if not p.exists():
            self._rebuild()
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("groups"), dict):
                raise ValueError("bad shape")
            self.state = {"sources": data.get("sources", {}), "groups": data["groups"], "alerts": data.get("alerts", {})}
            return []
        except ValueError:
            q = self.vault / "system" / "quarantine"
            q.mkdir(parents=True, exist_ok=True)
            dest = q / f"telemetry_state-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
            shutil.move(str(p), dest)
            self._rebuild()
            return [f"telemetry: state file was corrupt; moved to quarantine as {dest.name} and rebuilt from notes"]

    def _rebuild(self) -> None:
        self.state = {"sources": {}, "groups": {}, "alerts": {}}
        for p in sorted((self.vault / "raw" / "telemetry").glob("*.md")):
            d = frontmatter.parse(p.read_text(encoding="utf-8")).data or {}
            if d.get("type") != "production_error" or not d.get("fingerprint") or not d.get("source"):
                continue
            self.state["groups"][f"{d['source']}/{d['fingerprint']}"] = {
                "note": p.relative_to(self.vault).as_posix(), "first_seen": d.get("detected_at"),
                "last_seen": d.get("last_seen"), "count": int(d.get("count") or 0), "status": d.get("status", "active"),
                "kind": d.get("kind"), "sentry_id": (d.get("fingerprint") or "")[2:] if d.get("kind") == "sentry" else None}

    def save(self) -> None:
        _atomic(self.vault / STATE, json.dumps(self.state, indent=1, sort_keys=True))

    def _write_note(self, rel: str, fm: dict, body: str) -> None:
        lines = [f"{k}: {json.dumps(str(fm[k]), ensure_ascii=False)}" for k in NOTE_FIELDS if fm.get(k) not in (None, "")]
        lines[0] = "type: production_error"
        _atomic(self.vault / rel, "---\n" + "\n".join(lines) + "\n---\n" + body)

    def _body(self, g: dict, fm: dict) -> str:
        rows = "\n".join(f"| {k} | {v} |" for k, v in sorted((g.get("keys") or {}).items()))
        reopen = f"Reopen in ADX:\n\n```kql\n{g['reopen']}\n```\n" if g.get("reopen") else (
            f"Sentry: {fm['link']}\n" if fm.get("link") else "")
        tpl = (self.vault / "system/templates/production-error.md")
        text = tpl.read_text(encoding="utf-8") if tpl.exists() else "# {{exception}}\n\n{{key_rows}}\n\n{{reopen}}\n"
        for k, v in {"exception": fm["exception"], "environment": fm["environment"], "key_rows": rows,
                     "count": fm["count"], "detected_at": fm["detected_at"], "last_seen": fm["last_seen"],
                     "status": fm["status"], "reopen": reopen}.items():
            text = text.replace("{{" + k + "}}", str(v))
        return text

    def upsert(self, g: dict, now: datetime) -> str:
        key = f"{g['source']}/{g['fingerprint']}"
        old = self.state["groups"].get(key)
        rel = old["note"] if old else self.note_rel(g["source"], g["fingerprint"])
        if old:
            count = int(g["count"]) if g["kind"] == "sentry" else int(old.get("count", 0)) + int(g["count"])
            first = old.get("first_seen") or g["detected_at"]
            regressed = old.get("status") == "resolved"
        else:
            count, first, regressed = int(g["count"]), g["detected_at"], False
        fm = {"type": "production_error", "service": g["service"], "exception": g["exception"],
              "operation_id": g["operation_id"], "detected_at": first, "codebase": g["codebase"],
              "partition": g["partition"], "environment": g["environment"], "source": g["source"], "kind": g["kind"],
              "fingerprint": g["fingerprint"], "count": count, "last_seen": g["last_seen"], "status": "active",
              "substatus": g.get("substatus"), "regressed": "true" if regressed or g.get("substatus") == "regressed" else "false",
              "sentry_issue": g.get("sentry_issue"), "covered": "true" if g.get("covered") else "false",
              "culprit": g.get("culprit"), "link": g.get("link")}
        self._write_note(rel, fm, self._body(g, fm))
        self.state["groups"][key] = {"note": rel, "first_seen": first, "last_seen": g["last_seen"], "count": count,
                                     "status": "active", "kind": g["kind"],
                                     "sentry_id": g["fingerprint"][2:] if g["kind"] == "sentry" else None}
        return "updated" if old else "new"

    def set_status(self, key: str, status: str, now: datetime) -> None:
        grp = self.state["groups"][key]
        path = self.vault / grp["note"]
        note = frontmatter.parse(path.read_text(encoding="utf-8"))
        fm = dict(note.data or {})
        fm["status"] = status
        fm["resolved_at"] = now.isoformat() if status == "resolved" else None
        self._write_note(grp["note"], fm, note.body)
        grp["status"] = status

    def resolve_stale(self, source: str, now: datetime) -> int:
        n = 0
        for key, grp in list(self.state["groups"].items()):
            if not key.startswith(source + "/") or grp.get("status") != "active" or not grp.get("last_seen"):
                continue
            if now - datetime.fromisoformat(grp["last_seen"].replace("Z", "+00:00")) > QUIET:
                self.set_status(key, "resolved", now)
                n += 1
        return n

    def active(self, source: str) -> list:
        return [dict(grp, key=k) for k, grp in self.state["groups"].items()
                if k.startswith(source + "/") and grp.get("status") == "active"]
```

Each value is written as a JSON string, which is a valid YAML double-quoted scalar, so every value is quoted and keys are not (`count: "17"`); `type` stays unquoted for readability. `import yaml` is not needed in this module.

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_store.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add system/scripts/vaultlib/telemetry.py system/scripts/vaultlib/telemetry_store.py \
  system/tests/python/test_telemetry_core.py system/tests/python/test_telemetry_store.py
git commit -m "feat(telemetry): sources, windows, KQL, sanitized fingerprints, note store with rebuild"
```

---

### Task 6: The run and its CLI

**Files:**
- Create: `system/scripts/vaultlib/telemetry_run.py`, `system/scripts/telemetry_fetch.py`
- Test: `system/tests/python/test_telemetry_run.py`, `system/tests/telemetry.bats`, fixtures in `system/tests/fixtures/telemetry/`

**Interfaces:**
- Consumes: everything from Tasks 3–5.
- Produces: `telemetry_run.main(argv: list[str], vault: Path, now: datetime | None = None) -> int`; CLI flags `--source <name>`, `--check <name>`, `--dry-run`, `--list`; files `system/logs/telemetry-<YYYY-MM>.jsonl`, `system/logs/alerts_<date>.md` lines tagged `[telemetry]`, `system/telemetry.lock`.

- [ ] **Step 1: Write the failing pytest suite**

```python
# system/tests/python/test_telemetry_run.py
import json
from datetime import datetime, timedelta, timezone

import pytest

from helpers import write
from vaultlib import http, kusto, sentry, telemetry_run

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CB = '---\ntype: codebase\nname: "shop"\npath: "~"\npartition: "work"\nsearch_globs: ["*"]\n---\n'
ADX = ('---\ntype: telemetry_source\nname: "prod-adx"\ncodebase: "shop"\nenvironment: "prod"\nkind: "adx"\n'
       'adx_cluster: "https://example.kusto.windows.net"\nadx_database: "prod"\nadx_signals: ["logs"]\n{covers}---\n')
SEN = ('---\ntype: telemetry_source\nname: "prod-sentry"\ncodebase: "shop"\nenvironment: "prod"\nkind: "sentry"\n'
       'sentry_url: "https://sentry.example.com"\nsentry_org: "acme"\nsentry_projects: ["api"]\n---\n')
LOG_ROW = {"service": "api", "scope": "Shop.Orders", "event_id": "4012", "n": 3, "first": "2026-10-05T10:00:00Z",
           "last": "2026-10-05T11:00:00Z", "traces": 2, "sample_trace": "0af7651916cd43dd8448eb211c80319c"}


@pytest.fixture
def v(vault, monkeypatch):
    write(vault, "system/codebases/shop.md", CB)
    monkeypatch.setattr(kusto, "token", lambda c: "tok")
    return vault


def jsonl(v):
    return [json.loads(l) for l in (v / "system/logs/telemetry-2026-10.jsonl").read_text().splitlines()]


def test_adx_run_writes_note_logs_and_advances_checkpoint(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main([], v, NOW) == 0
    notes = list((v / "raw/telemetry").glob("prod-adx-a-*.md"))
    assert len(notes) == 1
    line = jsonl(v)[-1]
    assert line["source"] == "prod-adx" and line["new"] == 1 and line["exit"] == 0
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())
    assert state["sources"]["prod-adx"]["checkpoint"] == (NOW - timedelta(minutes=10)).isoformat()


def test_failed_source_keeps_checkpoint_and_does_not_double_count(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    telemetry_run.main([], v, NOW)
    def boom(*a, **k):
        raise http.TelemetryError("transient", "HTTP 503")
    monkeypatch.setattr(kusto, "query", boom)
    assert telemetry_run.main([], v, NOW + timedelta(hours=1)) == 1
    state = json.loads((v / "system/logs/telemetry_state.json").read_text())
    assert state["sources"]["prod-adx"]["checkpoint"] == (NOW - timedelta(minutes=10)).isoformat()
    assert state["sources"]["prod-adx"]["failures"] == 1


def test_three_failures_alert_once_a_day(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    def boom(*a, **k):
        raise http.TelemetryError("transient", "HTTP 503")
    monkeypatch.setattr(kusto, "query", boom)
    for h in range(5):
        telemetry_run.main([], v, NOW + timedelta(hours=h))
    alerts = (v / "system/logs/alerts_2026-10-05.md").read_text().splitlines()
    assert len([a for a in alerts if "[telemetry]" in a and "prod-adx" in a]) == 1


def test_auth_failure_alerts_immediately(v, monkeypatch):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    def noauth(c):
        raise http.TelemetryError("auth", "run az login")
    monkeypatch.setattr(kusto, "token", noauth)
    monkeypatch.setattr(kusto, "query", lambda *a, **k: kusto.token("x"))
    assert telemetry_run.main([], v, NOW) == 1
    assert "run az login" in (v / "system/logs/alerts_2026-10-05.md").read_text()


def test_covered_group_links_sentry_issue_and_lookup_cap(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers='covers: "prod-sentry"\n'))
    rows = [dict(LOG_ROW, event_id=str(1000 + i)) for i in range(25)]
    monkeypatch.setattr(kusto, "query", lambda *a, **k: rows)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    looked = []
    monkeypatch.setattr(sentry, "issue_for_trace", lambda b, o, t: looked.append(t) or {"id": "101", "shortId": "API-1"})
    telemetry_run.main([], v, NOW)
    assert len(looked) == 20
    covered = [n for n in (v / "raw/telemetry").glob("prod-adx-*.md") if 'covered: "true"' in n.read_text()]
    assert len(covered) == 20


def test_sentry_issue_resolved_in_sentry_resolves_note(v, monkeypatch):
    write(v, "system/telemetry/prod-sentry.md", SEN)
    monkeypatch.setattr(sentry, "project_ids", lambda *a: {"api": "7"})
    issue = {"id": "101", "shortId": "API-1", "permalink": "https://sentry.example.com/i/101/", "project": "api",
             "level": "error", "status": "unresolved", "substatus": "new", "firstSeen": "2026-10-05T10:00:00Z",
             "lastSeen": "2026-10-05T11:00:00Z", "count": "4", "type": "KeyError", "culprit": "a.py in f", "environment": "api"}
    monkeypatch.setattr(sentry, "issues", lambda *a: [issue])
    telemetry_run.main([], v, NOW)
    monkeypatch.setattr(sentry, "issues", lambda *a: [])
    monkeypatch.setattr(sentry, "issue_status", lambda *a: "resolved")
    telemetry_run.main([], v, NOW + timedelta(hours=1))
    assert 'status: "resolved"' in (v / "raw/telemetry/prod-sentry-s-101.md").read_text()


def test_dry_run_and_check_write_nothing(v, monkeypatch, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    monkeypatch.setattr(kusto, "query", lambda *a, **k: [LOG_ROW])
    assert telemetry_run.main(["--dry-run"], v, NOW) == 0
    assert telemetry_run.main(["--check", "prod-adx"], v, NOW) == 0
    assert not (v / "raw/telemetry").exists() or not list((v / "raw/telemetry").glob("*.md"))
    assert not (v / "system/logs/telemetry_state.json").exists()


def test_list_prints_enabled_sources(v, capsys):
    write(v, "system/telemetry/prod-adx.md", ADX.format(covers=""))
    write(v, "system/telemetry/off.md", ADX.format(covers="").replace('"prod-adx"', '"off"').replace("---\n", "enabled: \"false\"\n---\n", 2).replace("enabled: \"false\"\n---\n", "---\n", 1))
    assert telemetry_run.main(["--list"], v, NOW) == 0
    assert capsys.readouterr().out.split() == ["prod-adx"]


def test_usage_errors_exit_2(v):
    assert telemetry_run.main(["--bogus"], v, NOW) == 2
    assert telemetry_run.main(["--source", "nope"], v, NOW) == 2
```

(The `off.md` construction is awkward; write it out as its own literal string with `enabled: "false"` if you prefer. Keep `name` equal to the file stem.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest system/tests/python/test_telemetry_run.py -q`
Expected: FAIL (`ModuleNotFoundError: vaultlib.telemetry_run`).

- [ ] **Step 3: Implement `vaultlib/telemetry_run.py`**

```python
"""One telemetry fetch over every enabled source (Plan 11 spec §3, §5)."""
import argparse
import fcntl
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import kusto, sentry, telemetry as t
from .http import TelemetryError
from .telemetry_store import Store

LOCK = "system/telemetry.lock"
LOCK_WAIT = 120
MAX_GROUPS = 500
MAX_LOOKUPS = 20
MAX_STATUS = 20
FAIL_ALERT = 3


class Usage(Exception):
    pass


def _parser():
    p = argparse.ArgumentParser(prog="telemetry_fetch.py", add_help=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--source")
    g.add_argument("--check")
    g.add_argument("--list", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def _alert(vault: Path, store: Store, now: datetime, key: str, msg: str) -> None:
    day = now.astimezone().strftime("%Y-%m-%d")
    if store.state["alerts"].get(key) == day:
        return
    store.state["alerts"][key] = day
    path = vault / "system" / "logs" / f"alerts_{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"- {now.astimezone().strftime('%H:%M:%S')} [telemetry] {msg}\n")


def _log(vault: Path, now: datetime, line: dict) -> None:
    path = vault / "system" / "logs" / f"telemetry-{now.strftime('%Y-%m')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def _adx_groups(src, start, end, by_name, counters):
    groups = []
    for signal in src.adx_signals:
        kql = t.kql_logs(src, start, end, MAX_GROUPS) if signal == "logs" else t.kql_spans(src, start, end, MAX_GROUPS)
        rows = kusto.query(src.adx_cluster, src.adx_database, kql, MAX_GROUPS)
        if len(rows) >= MAX_GROUPS:
            total = kusto.query(src.adx_cluster, src.adx_database, t.kql_count(kql), 1)
            counters["truncated"] = int((total[0] if total else {}).get("Count", len(rows)))
        for r in rows:
            if signal == "logs":
                keys = {"service": t.sanitize(r.get("service")), "scope": t.sanitize(r.get("scope")),
                        "event_id": t.event_id(r.get("event_id"))}
                keys.update({k: t.sanitize(r.get(f"module_{i}")) for i, k in enumerate(src.adx_group_keys)})
                exception, kind = f"{keys['scope']}#{keys['event_id']}", "log"
                reopen_where = f'LogsAttributes["logrecord.event.id"] == "{keys["event_id"]}"'
            else:
                keys = {"service": t.sanitize(r.get("service")), "route": t.sanitize(r.get("route")),
                        "status": t.sanitize(r.get("status"))}
                exception, kind = f"{keys['route']} {keys['status']}", "span"
                reopen_where = f'SpanName has "{keys["route"].split(" ")[-1]}"'
            fp = t.fingerprint(src.name, kind, keys)
            groups.append({"fingerprint": fp, "source": src.name, "environment": src.environment, "codebase": src.codebase,
                           "partition": src.partition, "kind": kind, "service": keys["service"], "exception": exception,
                           "operation_id": t.trace_id(r.get("sample_trace")), "detected_at": str(r.get("first")),
                           "last_seen": str(r.get("last")), "count": int(r.get("n") or 0), "keys": keys,
                           "reopen": f"{'Logs' if kind == 'log' else 'Traces'}\n| where {reopen_where}"})
    return groups


def _cover(src, groups, by_name, store, counters):
    target = by_name.get(src.covers) if src.covers else None
    if not target:
        return
    lookups = 0
    for g in groups:
        if f"{g['source']}/{g['fingerprint']}" in store.state["groups"]:
            continue
        if lookups >= MAX_LOOKUPS:
            break
        lookups += 1
        hit = sentry.issue_for_trace(target.sentry_url, target.sentry_org, g["operation_id"])
        if hit:
            g["covered"], g["sentry_issue"] = True, hit["shortId"]
            counters["covered"] += 1


def _sentry_groups(src, start, store):
    ids = store.state["sources"].setdefault(src.name, {}).get("project_ids") or {}
    if set(ids) != set(src.sentry_projects):
        ids = sentry.project_ids(src.sentry_url, src.sentry_org, src.sentry_projects)
        store.state["sources"][src.name]["project_ids"] = ids
    out = []
    for i in sentry.issues(src.sentry_url, src.sentry_org, list(ids.values()), src.sentry_query, start):
        out.append({"fingerprint": f"s-{i['id']}", "source": src.name, "environment": src.environment,
                    "codebase": src.codebase, "partition": src.partition, "kind": "sentry",
                    "service": t.sanitize(i.get("environment") or i.get("project")),
                    "exception": t.sanitize(i.get("type") or "error"), "operation_id": str(i["id"]),
                    "detected_at": i.get("firstSeen"), "last_seen": i.get("lastSeen"), "count": int(i.get("count") or 0),
                    "keys": {"project": t.sanitize(i.get("project")), "level": t.sanitize(i.get("level"))},
                    "substatus": i.get("substatus"), "sentry_issue": i.get("shortId"),
                    "culprit": t.sanitize(i.get("culprit")), "link": str(i.get("permalink") or "").split("?")[0]})
    return out


def _run_source(vault, src, store, by_name, now, dry):
    st = store.state["sources"].setdefault(src.name, {})
    start, end, moved = t.window(st.get("checkpoint"), now, src.kind)
    counters = {"new": 0, "updated": 0, "resolved": 0, "covered": 0, "truncated": 0}
    groups = _adx_groups(src, start, end, by_name, counters) if src.kind == "adx" else _sentry_groups(src, start, store)
    if src.kind == "adx":
        _cover(src, groups, by_name, store, counters)
    if dry:
        for g in groups:
            print(json.dumps({k: g[k] for k in ("source", "fingerprint", "kind", "service", "exception", "count")}))
        return start, end, moved, counters
    for g in groups:
        counters[store.upsert(g, now)] += 1
    if src.kind == "sentry":
        seen = {g["fingerprint"] for g in groups}
        stale = sorted((g for g in store.active(src.name) if g["key"].split("/", 1)[1] not in seen),
                       key=lambda g: g.get("last_seen") or "")[:MAX_STATUS]
        for g in stale:
            if sentry.issue_status(src.sentry_url, src.sentry_org, g["sentry_id"]) == "resolved":
                store.set_status(g["key"], "resolved", now)
                counters["resolved"] += 1
    counters["resolved"] += store.resolve_stale(src.name, now)
    st["checkpoint"], st["failures"] = end.isoformat(), 0
    return start, end, moved, counters


def main(argv: list, vault: Path, now: datetime | None = None) -> int:
    vault = Path(vault)
    now = now or datetime.now(timezone.utc)
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    sources = t.load_sources(vault)
    by_name = {s.name: s for s in sources if s.enabled}
    if args.list:
        print("\n".join(by_name))
        return 0
    wanted = args.source or args.check
    if wanted and wanted not in by_name:
        print(f"telemetry_fetch: no enabled source named {wanted}")
        return 2
    if args.check:
        src = by_name[args.check]
        try:
            if src.kind == "adx":
                kusto.query(src.adx_cluster, src.adx_database, "print ok = 1", 1)
            else:
                sentry.project_ids(src.sentry_url, src.sentry_org, src.sentry_projects)
        except TelemetryError as exc:
            print(f"telemetry_fetch: {src.name}: {exc.reason}")
            return 1
        print(f"telemetry_fetch: {src.name}: ok")
        return 0
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / LOCK, "w") as lock:
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    print("telemetry_fetch: another fetch is running")
                    return 4
                time.sleep(1)
        store = Store(vault)
        if not args.dry_run:
            for w in store.load():
                _alert(vault, store, now, "state", w)
        rc = 0
        for src in [by_name[wanted]] if wanted else list(by_name.values()):
            line = {"started_at": now.isoformat(), "source": src.name}
            try:
                start, end, moved, counters = _run_source(vault, src, store, by_name, now, args.dry_run)
                line.update(window={"from": start.isoformat(), "to": end.isoformat()}, moved=moved, exit=0, **counters)
                if counters["truncated"]:
                    _alert(vault, store, now, f"{src.name}/truncated", f"{src.name}: {counters['truncated']} groups; only {MAX_GROUPS} kept")
            except TelemetryError as exc:
                rc = 1
                st = store.state["sources"].setdefault(src.name, {})
                st["failures"] = st.get("failures", 0) + 1
                line.update(exit=1, error=f"{exc.kind}: {exc.reason}")
                if exc.kind == "auth" or st["failures"] >= FAIL_ALERT:
                    _alert(vault, store, now, f"{src.name}/{exc.kind}", f"{src.name}: {exc.reason}")
            if not args.dry_run:
                _log(vault, now, line)
        if not args.dry_run:
            store.save()
        return rc
```

`system/scripts/telemetry_fetch.py`:

```python
#!/usr/bin/env python3
"""Fetch error groups from Sentry and ADX into raw/telemetry/ (Plan 11). Exit 0 ok, 1 a source failed, 2 usage, 4 busy."""
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import telemetry_run  # noqa: E402

sys.exit(telemetry_run.main(sys.argv[1:], VAULT))
```

`chmod +x system/scripts/telemetry_fetch.py`.

- [ ] **Step 4: Run the pytest suite**

Run: `python3 -m pytest system/tests/python/test_telemetry_run.py -q`
Expected: PASS. Fix the `off.md` literal if its construction trips.

- [ ] **Step 5: Write the bats suite with stub `az` and fixtures**

Fixtures (`system/tests/fixtures/telemetry/`): `kusto-logs.json` (the `V2` frame list from Task 3 with columns `service, scope, event_id, n, first, last, traces, sample_trace` and one row), `kusto-check.json` (a PrimaryResult with `ok = 1`).

```bash
#!/usr/bin/env bats
# telemetry_fetch.py end to end with a stub az and canned HTTP (Plan 11 spec §8).
load helpers

setup() {
  make_vault
  mkdir -p "$V/system/telemetry" "$V/system/codebases" "$BATS_TEST_TMPDIR/bin"
  cat > "$V/system/codebases/shop.md" <<'EOF'
---
type: codebase
name: "shop"
path: "~"
partition: "work"
search_globs: ["*"]
---
EOF
  cat > "$V/system/telemetry/prod-adx.md" <<'EOF'
---
type: telemetry_source
name: "prod-adx"
codebase: "shop"
environment: "prod"
kind: "adx"
adx_cluster: "https://example.kusto.windows.net"
adx_database: "prod"
adx_signals: ["logs"]
---
EOF
  printf '#!/bin/bash\necho tok\n' > "$BATS_TEST_TMPDIR/bin/az"
  chmod +x "$BATS_TEST_TMPDIR/bin/az"
  export PATH="$BATS_TEST_TMPDIR/bin:$PATH"
  export FOUNDRY_TELEMETRY_STUB="$BATS_TEST_TMPDIR/stub"
  cp -r "$REPO/system/tests/fixtures/telemetry" "$FOUNDRY_TELEMETRY_STUB"
  mkdir -p "$V/system/templates"
  cp "$REPO/system/templates/production-error.md" "$V/system/templates/"
}

@test "a run writes one note, a jsonl line and state" {
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 0 ]
  [ "$(find "$V/raw/telemetry" -name 'prod-adx-a-*.md' | wc -l)" -eq 1 ]
  grep -q '"source": "prod-adx"' "$V"/system/logs/telemetry-*.jsonl
  [ -f "$V/system/logs/telemetry_state.json" ]
}

@test "the lock is held: a second run exits 4" {
  exec 9> "$V/system/telemetry.lock"
  flock 9
  run env TELEMETRY_LOCK_WAIT=1 "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 4 ]
}

@test "az not logged in: exit 1 and one alert naming az login" {
  printf '#!/bin/bash\nexit 1\n' > "$BATS_TEST_TMPDIR/bin/az"
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$status" -eq 1 ]
  run "$V/system/scripts/telemetry_fetch.py"
  [ "$(grep -c 'run az login' "$V"/system/logs/alerts_*.md)" -eq 1 ]
}

@test "--check and --dry-run write no notes and no state" {
  run "$V/system/scripts/telemetry_fetch.py" --check prod-adx
  [ "$status" -eq 0 ]
  run "$V/system/scripts/telemetry_fetch.py" --dry-run
  [ "$status" -eq 0 ]
  [ ! -e "$V/system/logs/telemetry_state.json" ]
  [ "$(find "$V/raw" -path '*telemetry*' -name '*.md' 2>/dev/null | wc -l)" -eq 0 ]
}

@test "a Sentry token file readable by others is refused" {
  cat > "$V/system/telemetry/prod-sentry.md" <<'EOF'
---
type: telemetry_source
name: "prod-sentry"
codebase: "shop"
environment: "prod"
kind: "sentry"
sentry_url: "https://sentry.example.com"
sentry_org: "acme"
sentry_projects: ["api"]
---
EOF
  printf 'tok\n' > "$BATS_TEST_TMPDIR/sentry.token"
  chmod 0644 "$BATS_TEST_TMPDIR/sentry.token"
  run env FOUNDRY_SENTRY_TOKEN_FILE="$BATS_TEST_TMPDIR/sentry.token" "$V/system/scripts/telemetry_fetch.py" --check prod-sentry
  [ "$status" -eq 1 ]
  [[ "$output" == *"chmod 0600"* ]]
}
```

The lock test needs `LOCK_WAIT` to honour `TELEMETRY_LOCK_WAIT`: in `telemetry_run.py` set `LOCK_WAIT = int(os.environ.get("TELEMETRY_LOCK_WAIT", "120"))` (add `import os`). `make_vault` copies `system/scripts/` but not templates; the `setup` above copies the template.

- [ ] **Step 6: Run the bats suite**

Run: `bats system/tests/telemetry.bats`
Expected: 5 tests, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add system/scripts/vaultlib/telemetry_run.py system/scripts/telemetry_fetch.py system/tests/python/test_telemetry_run.py \
  system/tests/telemetry.bats system/tests/fixtures/telemetry
git commit -m "feat(telemetry): telemetry_fetch.py run with lock, alerts, run log, coverage and Sentry resolution"
```

---

### Task 7: Units and dependencies

**Files:**
- Create: `system/systemd/foundry-telemetry.service.in`, `system/systemd/foundry-telemetry.timer.in`
- Modify: `system/scripts/install_units.sh` (role case), `system/scripts/check_deps.sh`
- Test: `system/tests/units.bats`, `system/tests/setup.bats`

**Interfaces:**
- Consumes: `telemetry_fetch.py --list`.
- Produces: units `foundry-telemetry.service` / `.timer`, installed and enabled only on standalone or server with at least one enabled source; `check_deps` line `ok|optional az …`.

- [ ] **Step 1: Write the failing tests** (append to `units.bats`, reusing its existing setup that stubs `systemctl` and `systemd-analyze`)

```bash
@test "a vault with an enabled telemetry source gets the telemetry timer; one without does not" {
  run "$V/system/scripts/install_units.sh"
  [ "$status" -eq 0 ]
  [ ! -e "$SYSTEMD_USER_DIR/foundry-telemetry.timer" ]
  mkdir -p "$V/system/telemetry"
  printf -- '---\ntype: telemetry_source\nname: "p"\ncodebase: "x"\nenvironment: "prod"\nkind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n' > "$V/system/telemetry/p.md"
  run "$V/system/scripts/install_units.sh"
  [ "$status" -eq 0 ]
  grep -q '^OnUnitActiveSec=1h$' "$SYSTEMD_USER_DIR/foundry-telemetry.timer"
  grep -q 'telemetry_fetch.py' "$SYSTEMD_USER_DIR/foundry-telemetry.service"
  grep -q 'enable --now .*foundry-telemetry.timer' "$SYSTEMCTL_LOG"
}

@test "a server gets no sync drop-in for the telemetry service" {
  "$V/system/scripts/vault_index.py" set "$V/system/config.md" machine_role server
  mkdir -p "$V/system/telemetry"
  printf -- '---\ntype: telemetry_source\nname: "p"\ncodebase: "x"\nenvironment: "prod"\nkind: "adx"\nadx_cluster: "https://e"\nadx_database: "d"\n---\n' > "$V/system/telemetry/p.md"
  run "$V/system/scripts/install_units.sh"
  [ "$status" -eq 0 ]
  [ -e "$SYSTEMD_USER_DIR/foundry-telemetry.timer" ]
  [ ! -e "$SYSTEMD_USER_DIR/foundry-telemetry.service.d" ]
}
```

Use the names the existing `units.bats` setup defines for the unit directory and the `systemctl` call log (read its `setup()` first and substitute them for `SYSTEMD_USER_DIR` and `SYSTEMCTL_LOG` above).

In `setup.bats`, extend the PATH-stub test: add `az` to the stubbed binaries and assert `grep -qx "ok az"`; add a test that without `az` the line is `optional az …` and `--strict` still exits 0.

- [ ] **Step 2: Run to verify they fail**

Run: `bats system/tests/units.bats system/tests/setup.bats`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

`system/systemd/foundry-telemetry.service.in`:

```ini
[Unit]
Description=The Foundry: error telemetry fetch

[Service]
Type=oneshot
WorkingDirectory={{VAULT_ROOT}}
Environment="TZ={{TZ}}"
Environment="PATH={{UNIT_PATH}}"
TimeoutStartSec=20min
SuccessExitStatus=1 4
ExecStart="{{VAULT_ROOT}}/system/scripts/telemetry_fetch.py"
```

(`SuccessExitStatus=1 4`: a failed source is alerted by the script itself and must not mark the unit failed every hour.)

`system/systemd/foundry-telemetry.timer.in`:

```ini
[Unit]
Description=The Foundry: error telemetry every hour

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h

[Install]
WantedBy=timers.target
```

`install_units.sh`, right after the `esac` of the role case:

```bash
# Error telemetry (Plan 11): standalone and server, only when a source is enabled.
if [[ "$role" != client ]] && [[ -n "$(system/scripts/telemetry_fetch.py --list 2>/dev/null)" ]]; then
  UNITS+=(foundry-telemetry.service foundry-telemetry.timer)
  ENABLE+=(foundry-telemetry.timer)
fi
```

`check_deps.sh`: add `az) pkg_pacman=azure-cli pkg_apt=azure-cli ;;` to `hint()`, and after the `herdr tmux` loop:

```bash
if [[ "$role" != client ]]; then report az "$(has az)" optional; fi
```

- [ ] **Step 4: Run tests**

Run: `bats system/tests/units.bats system/tests/setup.bats`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add system/systemd/foundry-telemetry.service.in system/systemd/foundry-telemetry.timer.in \
  system/scripts/install_units.sh system/scripts/check_deps.sh system/tests/units.bats system/tests/setup.bats
git commit -m "feat(telemetry): hourly foundry-telemetry units when a source is enabled; az optional"
```

---

### Task 8: Brief prep, commands, Workcell and setup

**Files:**
- Modify: `system/scripts/brief_prep.sh`, `.claude/commands/brief.md`, `.claude/commands/debrief.md`, `.claude/commands/setup.md`, `system/agents/workcells/maintenance.md`
- Test: `system/tests/prep.bats`, `system/tests/commands.bats`

**Interfaces:**
- Consumes: `telemetry_fetch.py` exit codes; view `v_production_error` (built by the index from the schema).

- [ ] **Step 1: Write the failing tests**

`prep.bats` (the suite's `setup` already stubs the calendar):

```bash
@test "brief_prep: telemetry exit codes become Unavailable Sources lines; exit 0 adds none" {
  mkdir -p "$BATS_TEST_TMPDIR/tbin"
  for code in 0 1 4; do
    printf '#!/bin/bash\nexit %s\n' "$code" > "$V/system/scripts/telemetry_fetch.py"
    chmod +x "$V/system/scripts/telemetry_fetch.py"
    run "$V/system/scripts/brief_prep.sh" 2026-10-01
    [ "$status" -eq 0 ]
  done
  grep -qxF -- '- brief_prep: telemetry: a fetch was already running' "$IN/unavailable.md"
  run grep -c 'brief_prep: telemetry' "$IN/unavailable.md"
  [ "$output" -eq 1 ]
}

@test "brief_prep: a failed telemetry source is recorded" {
  printf '#!/bin/bash\nexit 1\n' > "$V/system/scripts/telemetry_fetch.py"
  chmod +x "$V/system/scripts/telemetry_fetch.py"
  run "$V/system/scripts/brief_prep.sh" 2026-10-01
  [ "$status" -eq 0 ]
  grep -qxF -- '- brief_prep: telemetry: a source failed (see system/logs/telemetry-2026-10.jsonl)' "$IN/unavailable.md"
}
```

`commands.bats`:

```bash
@test "/brief lists telemetry from v_production_error, new first, capped per environment" {
  f="$REPO/.claude/commands/brief.md"
  grep -qF 'v_production_error' "$f"
  grep -qF 'At most 10 rows per environment' "$f"
  grep -qF 'covered' "$f"
}

@test "/debrief reads the telemetry run log" {
  grep -qF 'system/logs/telemetry-<YYYY-MM>.jsonl' "$REPO/.claude/commands/debrief.md"
}

@test "/setup has a telemetry phase that is skipped on a client and checks each source" {
  sec="$(sed -n '/^## 6a\. Telemetry/,/^## 7\./p' "$REPO/.claude/commands/setup.md")"
  [[ "$sec" == *'telemetry_fetch.py --check'* ]]
  [[ "$sec" == *'0600'* ]]
  grep -qF 'skip phases 3, 6, 6a and 9' "$REPO/.claude/commands/setup.md"
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `bats system/tests/prep.bats system/tests/commands.bats`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

`brief_prep.sh`, after the calendar `case` block:

```bash
# Error telemetry (Plan 11 spec §6): a last fetch before the brief. Notes land in raw/telemetry/.
rc=0
system/scripts/telemetry_fetch.py > /dev/null 2>> "$PREP_DIR/prep_errors.log" || rc=$?
case "$rc" in
  0) ;;
  1) prep_unavailable "telemetry: a source failed (see system/logs/telemetry-${PREP_DATE:0:7}.jsonl)" ;;
  4) prep_unavailable "telemetry: a fetch was already running" ;;
  *) prep_unavailable "telemetry: telemetry_fetch.py failed (exit $rc; see $PREP_DIR/prep_errors.log)" ;;
esac
```

`.claude/commands/brief.md`, replace the `raw/telemetry/` input line with:

```markdown
- Telemetry: `system/scripts/vault_index.py query "SELECT path, environment, source, service, exception, count, detected_at, last_seen, substatus, regressed, sentry_issue, covered FROM v_production_error WHERE status = 'active' AND coalesce(mock, 0) = 0"`. Each is critical and routes to the Workcell with `telemetry`. Order environments by their source's `rank` (`SELECT name, environment, rank FROM v_telemetry_source`).
```

and in the Friction Matrix bullet, replace "telemetry" in Systemic Blockers with:

```markdown
telemetry (per environment: **New** first, meaning `detected_at` in the last 24 hours or `substatus` regressed or escalating or `regressed` true; then **Recurring**, other groups with `last_seen` in the last 24 hours, with their count; then one line with the number of groups whose `resolved_at` is in the last 24 hours. At most 10 rows per environment, then "and N more". Skip groups with `covered` true; their Sentry issue is listed. Each row: environment, service, exception, count, and the Sentry short ID or the note path.)
```

The resolved count needs `resolved_at`: add it to the query's column list.

`.claude/commands/debrief.md` inputs, add:

```markdown
- Telemetry runs: the lines of `system/logs/telemetry-<YYYY-MM>.jsonl` whose `started_at` begins with the date: per `source`, the sums of `new`, `updated`, `resolved`, and any line with `exit` 1 and its `error`.
```

and in **2. System State Deltas** add "telemetry runs per source (groups new, updated, resolved; failures)".

`.claude/commands/setup.md`: change "A client skips phases 3, 6 and 9" to "skip phases 3, 6, 6a and 9" (and the phase-0 text, and the report table list), and insert before `## 7. Index`:

```markdown
## 6a. Telemetry
Optional error monitoring from Sentry and Azure Data Explorer (Plan 11). Skipped on a client.
1. Show existing `system/telemetry/*.md` (except `example.md`) and ask whether to edit any. Never replace one.
2. For each registered codebase, ask whether it reports errors to Sentry, ADX, both or neither. For Sentry: the API base URL (for example `https://us.sentry.io`), the organization slug, and the project slugs per environment. For ADX: the cluster URL, the database, and per environment the resource-attribute filter that selects it (empty for a whole database). Ask for a `rank` per environment (lower is listed first in the brief) and, for an ADX source whose environment also has a Sentry source, whether it `covers` that source.
3. Sentry needs a read-only token (`event:read`, `project:read`, `org:read`). Ask the user to write it themselves: `! mkdir -p ~/.config/foundry && (umask 077; cat > ~/.config/foundry/sentry.token)`, paste, Ctrl-D. Never ask for the token in chat. Check it is mode 0600.
4. ADX uses the Azure CLI login: if `az account show` fails, ask the user to run `! az login`.
5. Write each source as `system/telemetry/<name>.md` (`<codebase>-<environment>-<kind>` by default), run `system/scripts/vault_index.py validate system/telemetry/<name>.md`, then `system/scripts/telemetry_fetch.py --check <name>`. On a failed check, set `enabled: "false"` and report its line.
6. If any source is enabled, re-run `system/scripts/install_units.sh --dry-run`, show the telemetry units, and install on an explicit yes (as in phase 5).
```

Also add "telemetry sources" to the phase 10 report table list.

`system/agents/workcells/maintenance.md`, extend the Production Telemetry bullet:

```markdown
  Start from the note's `culprit` (Sentry) or, for an ADX log group, look up its `event_id` in the codebase's log-event map entity note through the index (`vault_index.py related "<event_id>"`). Notes hold no message text: reopen the group in Sentry (`link`) or ADX (the note's KQL) for detail, and write findings to the wiki without IDs, messages or customer data.
```

- [ ] **Step 4: Run tests**

Run: `bats system/tests/prep.bats system/tests/commands.bats`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add system/scripts/brief_prep.sh .claude/commands/brief.md .claude/commands/debrief.md .claude/commands/setup.md \
  system/agents/workcells/maintenance.md system/tests/prep.bats system/tests/commands.bats
git commit -m "feat(telemetry): brief prep fetch, brief and debrief telemetry, setup phase 6a, Workcell guidance"
```

---

### Task 9: README, gate and live acceptance

**Files:**
- Modify: `README.md` (Status table row for Plan 11; Daily use; Requirements: `az` optional; Repository layout: `system/telemetry/`, `foundry-telemetry`; Security model: token file outside the vault, aggregates only)
- Create: `docs/superpowers/spikes/2026-10-xx-plan-11-acceptance.md`, `docs/superpowers/plans/2026-10-xx-plan-11-outcomes.md`

- [ ] **Step 1:** Update the README sections listed above. Keep the template rule: no organization or cluster names.
- [ ] **Step 2: Gate and lint**

Run: `system/scripts/verify_setup.sh > system/logs/gate.log 2>&1; echo "exit=$?"` then `sed -n '/===== summary/,$p' system/logs/gate.log`
Expected: `exit=0`, every suite PASS (17 suites with `telemetry.bats`).
Run: `system/scripts/lint_vault.sh > system/logs/lint.log 2>&1; echo "lint exit=$?"; tail -n 1 system/logs/lint.log`
Expected: `0 errors`.

- [ ] **Step 3: Commit, push the branch, open the PR** (the user approves before merge).

- [ ] **Step 4: Live acceptance on the real server, after the user merges and runs `update_template.sh`:**
  1. `/setup` phase 6a writes the sources (the user writes the Sentry token file).
  2. `system/scripts/telemetry_fetch.py --check <name>` for each source: all `ok`.
  3. `system/scripts/telemetry_fetch.py`: exit 0; count notes per source.
  4. Privacy scan (expect no output): `grep -rEn '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|\?[a-z]+=|skoid|sig=' raw/telemetry/ system/logs/telemetry_state.json system/logs/telemetry-*.jsonl`
  5. `/brief` for today shows the telemetry rows under Systemic Blockers.
  6. Record results in the acceptance note without IDs, names or counts that identify customers; write the outcomes note.
```
