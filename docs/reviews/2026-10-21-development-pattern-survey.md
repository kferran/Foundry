# Development pattern survey

**Date:** 2026-10-21. Template at master `1ca9198`.
**Used by:** the factory plan (`docs/superpowers/2026-10-21-factory-plan.md`) and its F0 and F1 specs.

Seven of nine connector features share one shape: a confined `claude -p` session (`lib_connector.sh`) → a deterministic stream checker (exit 1/3/6/7) → a parser of `structuredContent` → a cursor → a router (Now, alerts, brief, inbox) → an alert tag, `--check`, smoke row and unit. Telemetry is a second shape (HTTP poller, no model). The runner is shared; six helpers around it were re-implemented per feature.

## Feature matrix

S shared, R re-implemented, M manifest, H hard-coded in core, – absent.

| Feature | Conn | Checker | Cursor | Router | Redact | Tag | --check | Smoke | Unit | Stub |
|---|---|---|---|---|---|---|---|---|---|---|
| Inbox triage | S | R `triage.pages` | R jsonl ledger | Now, alerts | – (#288) | H | ✓ | H | H | calendar |
| Chat triage | S | same | same | Now, alerts | – | H | ✓ | H | H | calendar |
| Calendar | S + `--json-schema` | R `calendar_tsv.main` | – | brief | – | H | ✓ | H | – | calendar |
| Meetings | S | R `results` | R `.since` | raw → import | at import | H | ✓ | H | H | meetings |
| Notify | S | R `notify.check` | R state json | Slack | ✓ | H | ✓ (posts) | – | H | calendar |
| RCA filer | S | R `rca.extract` | `.attempt` | note, Now | – | M | – | – | – | calendar |
| Handoffs | S | R `jira.pages` | – | brief | – | M | ✓ | M | – | meetings |
| Intraday | S ×3 | R `query_pages` | R `common.state` | Now, alerts, today, inbox | today only | M | ✓ | M | M | watch |
| Telemetry | – (HTTP) | – | R `Store` | raw, alerts, Now | own masking | M | ✓ | M | M | – |

Re-implemented: the stream walker ×7 (`triage.py:162`, `watchlib/check.py:42`, `jira_handoffs.py:60`, `meetings_extract.py:46`, `notify.py:322`, `rca.py:140`, `calendar_tsv.py:110-148`); too-large detection only in calendar and the watch (triage mail still uses pageSize 50 `THREAD_VIEW_MINIMAL`, `triage_fetch.sh:111`, with no too-large check: probably the #289 loss, unconfirmed); `alert_once` ×8; `logline` ×6, `fail` ×5, `class Fail` ×6, `config()` ×6; deny lists per script; the ToolSearch prompt preamble ×9; a `stream()` fixture builder in 5 suites; 4 stub doubles; core units and smoke rows hard-coded (`install_units.sh:94-118`, `smoke_check.sh:120-128`). The F0 copy ratchet (`system/tests/conformance.bats`) holds the exact list from a grep of the tree.

## Recurring defect classes

| # | Class | PRs |
|---|---|---|
| C1 | Tool result too large, page caps | 176, 290, 292, 297, 272 |
| C2 | Now line length/format | 294, 139, 214, 255 |
| C3 | Timeout/timer arithmetic | 139, 176, 297, 278; #299 |
| C4 | Connector detection/confinement | 73, 137, 147, 252, 250 |
| C5 | Alert routing/alert-once | 295, 213, 208, 297, 226 |
| C6 | Lock/race | 153, 248, 247, 177 |
| C7 | Redaction of outside text | 183, 185, 154; #288, #298 |
| C8 | Names leaking | 233, 234, 286 |
| C9 | Extension manifest/loader gaps | 227, 238, 240, 226 |
| C10 | Tests that skip or flake | 199, 50, 278, 119 |
| C11 | Encoding/input bounds | 282, 254, 73 |
| C12 | Stale docs/roadmap | 274, 267, 129, 126 |
| C13 | CHANGELOG conflicts | 24565ff; about 42 master merges |

C1 and C2 were found by live use, not review. 99 of 662 commits mention "review"; most feature PRs end with a "final review fixes" commit.

## Stations

Probe (by hand) → grill, spec, plan, build (skills) → review (generic skill, no Foundry checklist) → acceptance (by hand; only ingest scripted) → PR and CHANGELOG (by hand) → live check (by hand; smoke covers `--check` only). Also by hand per feature: timeout arithmetic in comments, smoke row, unit block, alert tag, deny list, stub, the core budget raise (7 raises in about 5 days).

## Proposals

Libraries: `vaultlib/connector.py` (`check_stream`, `Fail`, `too_large`, `others`) from `watchlib/check.py:31-90`; `lib_fetch.sh` (`logline`, `alert_once`, `fail`, `skip`, `--check`, work-dir trap) from `triage_fetch.sh:50-69`; one stub dispatching on `--allowedTools` plus one `stream()` test builder; core features declare smoke, unit and tag in the manifest shape; `CHANGELOG.md merge=union`.
Skills: `connector-probe`, `new-fetch` (scaffold from the handoffs extension), `foundry-review` (diff checks per defect class), `live-acceptance`.
Tests: a timing-budget test (session timeouts × sessions + grace ≤ `TimeoutStartSec`; `--check` ≤ smoke timeout) and a manifest lint (`config_keys` = schema fields; every source has a smoke row).
