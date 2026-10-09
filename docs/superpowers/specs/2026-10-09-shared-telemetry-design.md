# Telemetry for shared services: an empty ADX filter value

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #94, part A only. Part B (the intraday brief) is held for a later grill; its chat and carry items folded into #98.

## 1. Problem

An ADX telemetry source selects its rows with `adx_filter`, for example `{instanceId: "U1"}`. Shared workers and APIs log without that attribute, so no source covers them. On 2026-10-09 a shared service failed from 04:57, and none of its roughly 1,700 Error rows in 7 days reached a brief.

`vaultlib/telemetry.py` renders each filter as `| where tostring(ResourceAttributes["<key>"]) == "<value>"`. `tostring()` of a missing attribute is `""`, so an empty value already selects rows where the attribute is missing or empty. Nothing documents it or pins it.

## 2. Decision

Document it and pin it with tests. No code change, and no new `/setup` question: the owner adds the extra source in their vault after the update.

## 3. Changes

- **`system/telemetry/example.md`:** a comment under `adx_filter` explaining that an empty value (`adx_filter: {instanceId: ""}`) selects the rows that lack the attribute (shared services), so a second source with the same database can cover them.
- **README (error telemetry section):** one sentence saying the same, and that the two sources should share an `environment` only if their rows cannot overlap (an instance filter and an empty filter never overlap).
- **`/setup` phase 6a:** one sentence after the ADX filter question: an empty value covers services that log without the attribute.

## 4. Tests

- **pytest (`test_telemetry_core.py`):** a source with `adx_filter: {instanceId: ""}` loads and lints clean, and its logs query, spans query and reopen query each contain `| where tostring(ResourceAttributes["instanceId"]) == ""`.
- **bats (`commands.bats`):** the README and setup text are present.

Bound tools: pytest, bats and the gate.
