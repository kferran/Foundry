# Telemetry for shared services: an empty ADX filter value

**Date:** 2026-10-09
**Status:** Draft for the owner's review.
**Issue:** #94, part A only. Part B (the intraday brief) is held for a later grill; its chat and carry items folded into #98.

## 1. Problem

An ADX telemetry source selects its rows with `adx_filter`, for example `{deployment.instance: "u1"}`. Shared workers and APIs log without that attribute, so no source covers them, and their failures never reach a brief.

`vaultlib/telemetry.py` renders each filter as `| where tostring(ResourceAttributes["<key>"]) == "<value>"`. `tostring()` of a missing attribute is `""`, so an empty value already selects rows where the attribute is missing or empty. Nothing documents it or pins it.

## 2. Decision

Document it and pin it with tests. No code change, and no new `/setup` question: the owner adds the extra source in their vault after the update.

## 3. Changes

- **`system/telemetry/example.md`:** a comment under `adx_filter` explaining that an empty value (`adx_filter: {deployment.instance: ""}`) selects the rows that lack the attribute (shared services), so a second source with the same database can cover them.
- **README (error telemetry section):** one sentence saying the same, and that a filter on one value and an empty filter on the same key never overlap, while a source with no filter overlaps both.
- **`/setup` phase 6a:** one sentence after the ADX filter question: an empty value covers services that log without the attribute.

## 4. Tests

- **pytest:** a source with `adx_filter: {deployment.instance: ""}` loads, and its logs, spans and reopen queries each contain `| where tostring(ResourceAttributes["deployment.instance"]) == ""` (`test_telemetry_core.py`); it lints clean (`test_telemetry_schema.py`); the reopen query stored in a note keeps it (`test_telemetry_store.py`).
- **bats (`commands.bats`):** the README and setup text are present.

Bound tools: pytest, bats and the gate.
