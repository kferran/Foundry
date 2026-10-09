# Telemetry: a source for shared services that log without the instance attribute

**Date:** 2026-10-09
**Status:** Approved by the owner, 2026-10-09.
**Issue:** #94, part A. Part B (intraday brief) has its own spec, `2026-10-09-intraday-brief-design.md`.

## 1. Problem

An ADX database can hold several environments, told apart by a resource attribute that each source filters on (`adx_filter: {instanceId: "U1"}`). Shared services in the same database (workers and APIs that serve more than one environment) log without that attribute, so no source selects their rows. In one vault the shared services logged about 1,700 Error rows in 7 days and none reached a brief, including an outage that began an hour before the brief ran.

The fetch already handles this case. `adx_filter: {instanceId: ""}` renders `| where tostring(ResourceAttributes["instanceId"]) == ""`, and Kusto's `tostring()` of a missing attribute is `""`, so the filter selects rows where the attribute is missing or empty. Checked 2026-10-09: the value parses, lints clean and renders in the logs, spans and reopen KQL. Neither the docs nor `/setup` mention it, and no test pins it.

## 2. Change

- `system/telemetry/example.md` documents the empty-value filter and when to use it.
- `/setup` phase 6a, step 2: for an ADX database with a per-environment filter, ask whether some services log without the filtered attribute. On yes, offer one more source, `<codebase>-<environment>-shared-adx`, with that attribute set to `""`, the environment the user names for it, and a `rank` just after that environment's source. Its body says the groups can include traffic from every environment in the database.
- No change to the fetch code.

## 3. Tests

- `test_telemetry_core.py`: a source file with `adx_filter: {instanceId: ""}` loads with that value, and `kql_logs`, `kql_spans` and `kql_reopen` each carry the `== ""` line.
- `test_telemetry_schema.py`: the same source lints clean.
- `commands.bats`: phase 6a asks about shared services and names the `-shared-adx` source.

The two Python tests pass on the current code. Each is shown to fail by a temporary change that drops empty filter values, then reverted. The `commands.bats` test fails before the `/setup` text changes. Bound tools: pytest (`test_telemetry_core.py`, `test_telemetry_schema.py`), bats (`commands.bats`) and the gate (`system/scripts/verify_setup.sh`).

## 4. Vault follow-up

After the update, a vault adds its shared-services source by re-running `/setup` phase 6a, or by writing the file by hand and running `system/scripts/vault_index.py validate` and `system/scripts/telemetry_fetch.py --check <name>`.
