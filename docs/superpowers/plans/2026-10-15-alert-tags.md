# Alert Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slack carries only the alert tags the owner can act on now; the rest waits for the brief; a session can push one line to the owner (#158).

**Architecture:** `vaultlib/alerts.py` holds the tag registry and `severity(line)`. `notify.py collect()` keeps only `now` lines. `system/scripts/alert.py <tag> <text>` appends a line. A drift test keeps every tag a writer uses in the registry.

**Tech Stack:** Python 3 stdlib, bats, pytest.

**Spec:** `docs/superpowers/specs/2026-10-14-alert-tags-design.md`. Owner decisions on #158 (2026-10-15): the table as proposed; no `notify_now_tags` override.

## Global Constraints

- Severity table (spec §2), verbatim: now = foreman, orders, sync, update, rca, intake, triage (as a count); brief = commit_runs, smoke, calendar, meetings, handoffs, telemetry, dtcc, memory; never = notify. Untagged or unknown tag = brief.
- The once-a-day dedupe and the 200-character cut stay.
- Settings change (one allow rule): feature lane, live acceptance before merge.
- bats ruling R1; template rule (no names, hosts, user paths).

## Rulings

- **R1 An allow rule for the push.** `Bash(system/scripts/alert.py foreman:*)` joins `.claude/settings.json`, so the Foreman pushes without a prompt (the owner's outcome: "the Foreman can push a line to the owner on its own"). It writes one local line; the notifier, which already runs unattended, does the posting. Other tags stay a prompt. Cost if wrong: one rule to remove.
- **R2 The alert line's day and time are local**, like every other writer (`date +%H:%M:%S`, `now.astimezone()`).

## Review Focus

1. A `[calendar]` expired-credential line (connector health) no longer reaches Slack; the brief's Sources line carries it (Task 1 test asserts brief severity).
2. `[triage]` lines still go out as a count (Task 1 test).
3. `alert.py` text with a newline or control characters cannot forge a second alert line (Task 2 test).
4. A line whose tag has uppercase or digits (`[Sync]`) is brief, never now (Task 1 test).
5. A new writer with a new tag fails the drift test until the registry has it (Task 2 test).

---

### Task 1: Registry and notifier

**Files:** Create `system/scripts/vaultlib/alerts.py`; modify `system/scripts/vaultlib/notify.py` (`collect`). Tests: create `system/tests/python/test_alerts.py`; modify `system/tests/python/test_notify.py`.

- [ ] Failing tests: `severity` per table row, untagged, unknown tag, `[Sync]`; `collect` skips a `[smoke]` line and keeps a `[sync]` line, `[triage]` still a count, `[notify]` never.
- [ ] Implement:

```python
"""The alert tags (alert tags spec §2): who raises each one and whether Slack carries it now or it waits for the
brief. notify.py sends only `now` lines; an untagged line or a tag outside the table waits for the brief."""
import re

TAGS = {
    "foreman": ("a session's message to the owner", "now"),
    "orders": ("a Work Order that needs the owner, the self-test, the sandbox", "now"),
    "sync": ("sync blocked, a failed merge or push", "now"),
    "update": ("the daily template update", "now"),
    "rca": ("a ticket filed, or a filing that stopped", "now"),
    "intake": ("a failed brief or debrief, a publish refused, an input quarantined", "now"),
    "triage": ("mail that needs the owner (sent as a count)", "now"),
    "commit_runs": ("a run the hook refused", "brief"),
    "smoke": ("the smoke check", "brief"),
    "calendar": ("the calendar fetch", "brief"),
    "meetings": ("the meetings fetch", "brief"),
    "handoffs": ("the Jira handoffs fetch", "brief"),
    "telemetry": ("the telemetry fetch", "brief"),
    "dtcc": ("the DTCC watcher", "brief"),
    "memory": ("the memory hooks", "brief"),
    "notify": ("the notifier itself", "never"),
}
LINE = re.compile(r"^- \d\d:\d\d:\d\d \[([a-z_]+)\] ")


def severity(line: str) -> str:
    m = LINE.match(line)
    return TAGS[m.group(1)][1] if m and m.group(1) in TAGS else "brief"
```

`collect`: `if not x.startswith("- ") or alerts.severity(x) != "now": continue` (replaces the `TAG in x` test).
- [ ] Green: `test.sh system/tests/python/test_alerts.py`, `test_notify.py`. Commit `feat(notify): Slack carries the now alert tags; the rest waits for the brief (#158)`.

### Task 2: `alert.py` and the drift test

**Files:** Create `system/scripts/alert.py` (executable). Tests: `system/tests/scripts.bats` (alert.py appends, refuses an unknown tag with exit 2, a newline in the text stays on one line; drift test over `system/scripts/**` and `system/hooks/**` for the `printf -- '- %s [tag]` and `f"- {…} [tag]` forms, every tag a key of TAGS).
- [ ] Failing tests, then:

```python
#!/usr/bin/env python3
"""Append one alert line (alert tags spec §3.3). Exit 0 written, 2 usage: a tag outside the table or empty text.

  alert.py <tag> <text>    a session uses the foreman tag to tell the owner something now
"""
```
It writes `- HH:MM:SS [tag] <text>` to `system/logs/alerts_<YYYY-MM-DD>.md` (local time), control characters replaced by spaces.
- [ ] Green; commit `feat(alerts): alert.py writes one tagged line; a drift test keeps the registry complete (#158)`.

### Task 3: Documents and the allow rule

**Files:** `CLAUDE.md` (Now rule sentence), `FOUNDRY.md` (Slack notices table and sentence; Daily use push sentence), `.claude/commands/brief.md` (Pipeline grouped by tag), `.claude/settings.json` (R1), notices spec §2 and §3.1 lines, `system/tests/commands.bats`, `system/tests/vault_integrity.bats`.
- [ ] Failing commands.bats/vault_integrity.bats assertions, text, green, commit `docs(alerts): the tag table, the Foreman push and the brief's Pipeline by tag (#158)`.

### Task 4: Gate, review, acceptance, PR

- [ ] `verify_setup.sh` (sandbox off) green; fresh Opus review; live acceptance: in a throwaway clone, `alert.py foreman "test"` and a `[smoke]` line, then `notify.py collect` (never `notify.sh`, which posts) shows only the foreman line; a headless brief lists both under Pipeline by tag. PR "Part of #158" (closes it with the note half merged).
